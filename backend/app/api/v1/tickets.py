from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.authz import AuthPrincipal, CurrentPrincipal, ensure_project_access, list_accessible_project_ids, require_roles
from app.api.dependencies import DbSession
from app.domain.value_objects.ticket_status import TicketStatus
from app.models.ticket import Ticket
from app.schemas.common import PaginatedResponse
from app.schemas.ticket import TicketCreate, TicketQualityReport, TicketResponse, TicketUpdate

router = APIRouter(prefix="/tickets", tags=["Tickets"])


@router.get("", response_model=PaginatedResponse[TicketResponse])
async def list_tickets(
    session: DbSession,
    principal: CurrentPrincipal,
    project_id: int | None = Query(None),
    sprint_id: int | None = Query(None),
    status: TicketStatus | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    provider: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
) -> PaginatedResponse[TicketResponse]:
    from sqlalchemy import and_, select, func
    from dateutil.parser import parse as parse_date
    from app.services.trello.live_project_service import TrelloLiveProjectService

    if provider is not None and provider != "trello":
        return PaginatedResponse(items=[], total=0, page=page, page_size=page_size)

    offset = (page - 1) * page_size
    filters = []
    if project_id:
        await ensure_project_access(session, principal, project_id)
        filters.append(Ticket.project_id == project_id)
    else:
        accessible_ids = await list_accessible_project_ids(session, principal)
        if accessible_ids is not None:
            filters.append(Ticket.project_id.in_(accessible_ids or [-1]))
    if sprint_id:
        filters.append(Ticket.sprint_id == sprint_id)
    if status:
        filters.append(Ticket.status == status.value)
    if start_date:
        filters.append(Ticket.last_activity_at >= parse_date(start_date))
    if end_date:
        filters.append(Ticket.last_activity_at <= parse_date(end_date))

    from sqlalchemy import select as sa_select
    count_stmt = sa_select(func.count()).select_from(Ticket)
    list_stmt = sa_select(Ticket)
    if filters:
        count_stmt = count_stmt.where(and_(*filters))
        list_stmt = list_stmt.where(and_(*filters))

    list_stmt = list_stmt.order_by(Ticket.updated_at.desc()).offset(offset).limit(page_size)

    total_result = await session.execute(count_stmt)
    items_result = await session.execute(list_stmt)
    total = total_result.scalar_one()
    items = list(items_result.scalars().all())

    if project_id and total == 0:
        live_service = TrelloLiveProjectService(session)
        live_items = await live_service.list_ticket_responses(
            project_id,
            offset=offset,
            limit=page_size,
            start_date=start_date,
            end_date=end_date,
        )
        if live_items:
            total = await live_service.count_live_tickets(project_id, start_date=start_date, end_date=end_date)
            return PaginatedResponse(
                items=live_items,
                total=total,
                page=page,
                page_size=page_size,
            )

    return PaginatedResponse(
        items=[TicketResponse.model_validate(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=TicketResponse, status_code=201)
async def create_ticket(
    body: TicketCreate,
    session: DbSession,
    principal: AuthPrincipal = Depends(
        require_roles(
            "super_admin",
            "company_admin",
            "company_manager",
            "client_admin",
            "client_pm",
            "esn_admin",
            "esn_delivery_manager",
        )
    ),
) -> TicketResponse:
    await ensure_project_access(session, principal, body.project_id)
    ticket = Ticket(**body.model_dump())
    session.add(ticket)
    await session.flush()
    await session.refresh(ticket)
    return TicketResponse.model_validate(ticket)


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(ticket_id: int, session: DbSession, principal: CurrentPrincipal) -> TicketResponse:
    from sqlalchemy import select

    from app.models.trello_board import TrelloBoard
    from app.models.trello_card import TrelloCard
    from app.models.trello_credential import TrelloCredential
    from app.repositories.ticket_repository import TicketRepository
    from app.services.trello.live_project_service import TrelloLiveProjectService

    repo = TicketRepository(session)
    ticket = await repo.get_with_relations(ticket_id)
    if not ticket:
        result = await session.execute(
            select(TrelloCredential.project_id)
            .join(TrelloBoard, TrelloBoard.credential_id == TrelloCredential.id)
            .join(TrelloCard, TrelloCard.board_id == TrelloBoard.id)
            .where(TrelloCard.id == ticket_id)
        )
        project_id = result.scalar_one_or_none()
        if project_id is None:
            raise HTTPException(status_code=404, detail="Ticket not found.")
        await ensure_project_access(session, principal, project_id)

        live_ticket = await TrelloLiveProjectService(session).get_ticket_response(project_id, ticket_id)
        if live_ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found.")
        return live_ticket
    await ensure_project_access(session, principal, ticket.project_id)
    return TicketResponse.model_validate(ticket)


@router.patch("/{ticket_id}", response_model=TicketResponse)
async def update_ticket(
    ticket_id: int,
    body: TicketUpdate,
    session: DbSession,
    principal: AuthPrincipal = Depends(
        require_roles(
            "super_admin",
            "company_admin",
            "company_manager",
            "client_admin",
            "client_pm",
            "esn_admin",
            "esn_delivery_manager",
        )
    ),
) -> TicketResponse:
    from app.repositories.ticket_repository import TicketRepository

    repo = TicketRepository(session)
    ticket = await repo.get_by_id(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    await ensure_project_access(session, principal, ticket.project_id)

    update_data = body.model_dump(exclude_unset=True)

    # Validate status transitions
    if "status" in update_data:
        current = TicketStatus(ticket.status)
        target = TicketStatus(update_data["status"])
        if not current.can_transition_to(target):
            raise HTTPException(
                status_code=422,
                detail=f"Invalid transition: {current} → {target}",
            )

    ticket = await repo.update(ticket, **update_data)
    await repo.touch_activity(ticket_id)
    return TicketResponse.model_validate(ticket)


@router.get("/{ticket_id}/quality", response_model=TicketQualityReport)
async def get_ticket_quality(ticket_id: int, session: DbSession, principal: CurrentPrincipal) -> TicketQualityReport:
    from app.repositories.ticket_repository import TicketRepository
    from app.services.ticket_monitoring_service import TicketMonitoringService

    repo = TicketRepository(session)
    ticket = await repo.get_by_id(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    await ensure_project_access(session, principal, ticket.project_id)

    svc = TicketMonitoringService(session)
    return svc.evaluate_ticket_quality(ticket)


@router.post("/scan", summary="Trigger manual ticket quality scan")
async def trigger_scan(
    session: DbSession,
    principal: AuthPrincipal = Depends(
        require_roles(
            "super_admin",
            "company_admin",
            "company_manager",
            "client_admin",
            "client_pm",
            "esn_admin",
            "esn_delivery_manager",
        )
    ),
) -> dict:
    from app.services.ticket_monitoring_service import TicketMonitoringService

    del principal
    svc = TicketMonitoringService(session)
    reports = await svc.scan_all_active_tickets()
    low_quality = [r for r in reports if r.quality_score < 60]
    return {
        "scanned": len(reports),
        "low_quality_count": len(low_quality),
        "avg_score": sum(r.quality_score for r in reports) / len(reports) if reports else 0,
    }

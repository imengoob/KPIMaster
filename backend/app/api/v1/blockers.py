from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.api.authz import AuthPrincipal, CurrentPrincipal, ensure_project_access, require_roles

from app.api.dependencies import DbSession
from app.schemas.blocker import BlockerResponse, BlockerSummary, EnrichedBlockerResponse

router = APIRouter(prefix="/blockers", tags=["Blockers"])


@router.get("", response_model=list[EnrichedBlockerResponse])
async def list_blockers(
    session: DbSession,
    principal: CurrentPrincipal,
    project_id: int | None = Query(None),
    include_resolved: bool = Query(False),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    provider: str | None = Query(None),
) -> list[EnrichedBlockerResponse]:
    from dateutil.parser import parse as parse_date
    """
    Returns blockers enriched with ticket title and assignee_id.
    Matches the frontend BackendBlocker interface exactly.
    """
    from sqlalchemy.orm import selectinload

    from app.models.blocker import Blocker
    from app.models.ticket import Ticket
    from app.services.trello.live_project_service import TrelloLiveProjectService

    if provider is not None and provider != "trello":
        return []

    if project_id is not None:
        await ensure_project_access(session, principal, project_id)
    stmt = select(Blocker).options(selectinload(Blocker.ticket))

    if not include_resolved:
        stmt = stmt.where(Blocker.resolved_at.is_(None))

    if project_id is not None:
        stmt = stmt.join(Blocker.ticket).where(Ticket.project_id == project_id)

    result = await session.execute(stmt)
    blockers = list(result.scalars().all())

    from app.api.authz import get_allowed_kpi_subject_ids
    allowed_ids = await get_allowed_kpi_subject_ids(session, principal, project_id)

    if allowed_ids is not None:
        from app.api.authz import member_numeric_id
        valid_blockers = []
        for b in blockers:
            if not b.ticket or not b.ticket.assignee_id:
                continue
            numeric = member_numeric_id(b.ticket.assignee_id)
            if numeric in allowed_ids:
                valid_blockers.append(b)
        blockers = valid_blockers

    if project_id is not None and not blockers:
        live_blockers = await TrelloLiveProjectService(session).list_blockers(
            project_id,
            start_date=start_date,
            end_date=end_date,
        )
        if live_blockers:
            if allowed_ids is not None:
                filtered_live = []
                for lb in live_blockers:
                    if not lb.ticket_assignee_id:
                        continue
                    # lb.ticket_assignee_id is already the numeric hash
                    if lb.ticket_assignee_id in allowed_ids:
                        filtered_live.append(lb)
                return filtered_live
            return live_blockers

    return [
        EnrichedBlockerResponse(
            id=b.id,
            ticket_id=b.ticket_id,
            ticket_title=b.ticket.title if b.ticket else f"Ticket #{b.ticket_id}",
            ticket_assignee_id=b.ticket.assignee_id if b.ticket else None,
            description=b.description,
            stall_hours=b.stall_hours,
            escalation_level=b.escalation_level,
            detected_at=b.detected_at,
            last_escalated_at=b.last_escalated_at,
            resolved_at=b.resolved_at,
            created_at=b.created_at,
            updated_at=b.updated_at,
        )
        for b in blockers
    ]


@router.get("/summary", response_model=BlockerSummary)
async def get_blocker_summary(
    session: DbSession,
    principal: AuthPrincipal = Depends(
        require_roles(
            "super_admin",
            "company_admin",
            "company_manager",
            "client_admin",
            "client_exec",
            "client_pm",
            "esn_admin",
            "esn_delivery_manager",
            "auditor_readonly",
        )
    ),
) -> BlockerSummary:
    from app.repositories.blocker_repository import BlockerRepository

    del principal
    repo = BlockerRepository(session)
    stats = await repo.get_summary_stats()
    return BlockerSummary(**stats)


@router.get("/{blocker_id}", response_model=BlockerResponse)
async def get_blocker(blocker_id: int, session: DbSession, principal: CurrentPrincipal) -> BlockerResponse:
    from app.repositories.blocker_repository import BlockerRepository
    from app.models.ticket import Ticket

    repo = BlockerRepository(session)
    blocker = await repo.get_by_id(blocker_id)
    if not blocker:
        raise HTTPException(status_code=404, detail="Blocker not found.")
    ticket = await session.get(Ticket, blocker.ticket_id)
    if ticket is not None:
        await ensure_project_access(session, principal, ticket.project_id)
    return BlockerResponse.model_validate(blocker)

from pydantic import BaseModel
class BlockerActionRequest(BaseModel):
    action_type: str
@router.post("/{blocker_id}/action", response_model=BlockerResponse)
async def action_blocker(
    blocker_id: int,
    body: BlockerActionRequest,
    session: DbSession,
    principal: CurrentPrincipal,
) -> BlockerResponse:
    from app.repositories.blocker_repository import BlockerRepository
    from sqlalchemy import func

    repo = BlockerRepository(session)
    blocker = await repo.get_by_id(blocker_id)
    if not blocker:
        raise HTTPException(status_code=404, detail="Blocker not found.")

    act = body.action_type
    if act == "prompt_developer":
        blocker.escalation_level = max(blocker.escalation_level, 1)
    elif act == "alert_lead":
        blocker.escalation_level = max(blocker.escalation_level, 2)
    elif act in ["escalate_management", "escalate"]:
        blocker.escalation_level = max(blocker.escalation_level, 3)
    else:
        raise HTTPException(status_code=400, detail="Unknown action type.")

    blocker.last_escalated_at = func.now()
    await session.commit()
    await session.refresh(blocker)

    return BlockerResponse.model_validate(blocker)

@router.post("/{blocker_id}/resolve", response_model=BlockerResponse)
async def resolve_blocker(
    blocker_id: int,
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
) -> BlockerResponse:
    from app.services.blocker_detection_service import BlockerDetectionService
    from app.repositories.blocker_repository import BlockerRepository
    from app.models.ticket import Ticket

    blocker = await BlockerRepository(session).get_by_id(blocker_id)
    if blocker is None:
        raise HTTPException(status_code=404, detail="Blocker not found.")
    ticket = await session.get(Ticket, blocker.ticket_id)
    if ticket is not None:
        await ensure_project_access(session, principal, ticket.project_id)
    svc = BlockerDetectionService(session)
    blocker = await svc.resolve_blocker(blocker_id)
    if not blocker:
        raise HTTPException(status_code=404, detail="Blocker not found.")
    return BlockerResponse.model_validate(blocker)


@router.post("/detect", summary="Manually trigger blocker detection sweep")
async def trigger_detection(
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
    from app.services.blocker_detection_service import BlockerDetectionService

    del principal
    svc = BlockerDetectionService(session)
    stats = await svc.run_detection_sweep()
    return stats
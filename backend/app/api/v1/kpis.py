from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.authz import AuthPrincipal, CurrentPrincipal, ensure_project_access, require_roles
from app.api.dependencies import DbSession
from app.schemas.kpi import KPIDashboard, KPIResponse

router = APIRouter(prefix="/kpis", tags=["KPIs"])


def _as_date(value: str | None):
    if not value:
        return None
    from dateutil.parser import parse as parse_date

    return parse_date(value).date()


@router.get("", response_model=KPIDashboard)
async def get_kpis(
    session: DbSession,
    principal: CurrentPrincipal,
    project_id: int = Query(..., description="Project ID"),
    sprint_id: int | None = Query(None, description="Sprint ID (defaults to current active sprint)"),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
) -> KPIDashboard:
    from app.repositories.sprint_repository import SprintRepository
    from app.services.kpi_service import KPIService
    from app.services.trello.live_project_service import TrelloLiveProjectService

    await ensure_project_access(session, principal, project_id)
    if sprint_id is None:
        sprint_repo = SprintRepository(session)
        sprint = (
            await sprint_repo.get_sprint_for_range(
                project_id,
                start_date=_as_date(start_date),
                end_date=_as_date(end_date),
            )
            if start_date or end_date
            else await sprint_repo.get_active_sprint(project_id)
        )
        if sprint:
            sprint_id = sprint.id

    svc = KPIService(session)
    dashboard = await svc.get_dashboard(project_id, sprint_id)
    if dashboard.current_kpis is not None or dashboard.sprint_id is not None:
        return dashboard

    live_dashboard = await TrelloLiveProjectService(session).build_dashboard(project_id, start_date, end_date)
    if live_dashboard is not None:
        return live_dashboard
    return dashboard


@router.post("/compute", response_model=KPIResponse, summary="Force KPI recomputation")
async def compute_kpis(
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
    project_id: int = Query(...),
    sprint_id: int = Query(...),
) -> KPIResponse:
    from app.services.kpi_service import KPIService

    await ensure_project_access(session, principal, project_id)
    svc = KPIService(session)
    try:
        snapshot = await svc.compute_and_persist(project_id, sprint_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return KPIResponse.model_validate(snapshot)


@router.get("/history")
async def kpi_history(
    session: DbSession,
    principal: CurrentPrincipal,
    project_id: int = Query(...),
    limit: int = Query(10, ge=1, le=50),
):
    from sqlalchemy import select
    from app.models.kpi_snapshot import KPISnapshot

    await ensure_project_access(session, principal, project_id)
    stmt = (
        select(KPISnapshot)
        .where(KPISnapshot.project_id == project_id)
        .order_by(KPISnapshot.computed_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    snapshots = list(result.scalars().all())
    return [KPIResponse.model_validate(s) for s in snapshots]

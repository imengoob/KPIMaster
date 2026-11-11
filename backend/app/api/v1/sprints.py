from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.authz import AuthPrincipal, CurrentPrincipal, ensure_project_access, require_roles
from app.api.dependencies import DbSession
from app.models.sprint import Sprint
from app.schemas.sprint import SprintCreate, SprintResponse, SprintUpdate

router = APIRouter(prefix="/sprints", tags=["Sprints"])


@router.post("", response_model=SprintResponse, status_code=201)
async def create_sprint(
    body: SprintCreate,
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
) -> SprintResponse:
    from app.repositories.sprint_repository import SprintRepository

    await ensure_project_access(session, principal, body.project_id)
    repo = SprintRepository(session)
    existing = await repo.get_active_sprint(body.project_id)
    if existing and body.status != "planning":
        raise HTTPException(
            status_code=409,
            detail="An active sprint already exists for this project. Complete it first.",
        )

    sprint = Sprint(**body.model_dump())
    sprint = await repo.create(sprint)
    return SprintResponse.model_validate(sprint)


@router.get("/{sprint_id}", response_model=SprintResponse)
async def get_sprint(sprint_id: int, session: DbSession, principal: CurrentPrincipal) -> SprintResponse:
    from app.repositories.sprint_repository import SprintRepository

    repo = SprintRepository(session)
    sprint = await repo.get_by_id(sprint_id)
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found.")
    await ensure_project_access(session, principal, sprint.project_id)
    return SprintResponse.model_validate(sprint)


@router.patch("/{sprint_id}", response_model=SprintResponse)
async def update_sprint(
    sprint_id: int,
    body: SprintUpdate,
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
) -> SprintResponse:
    from app.repositories.sprint_repository import SprintRepository

    repo = SprintRepository(session)
    sprint = await repo.get_by_id(sprint_id)
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found.")
    await ensure_project_access(session, principal, sprint.project_id)

    sprint = await repo.update(sprint, **body.model_dump(exclude_unset=True))
    return SprintResponse.model_validate(sprint)


@router.get("/{sprint_id}/burndown")
async def get_burndown(sprint_id: int, session: DbSession, principal: CurrentPrincipal):
    from app.services.burndown_service import BurndownService
    from app.schemas.burndown import BurndownChart
    from app.services.trello.live_project_service import TrelloLiveProjectService
    from app.repositories.sprint_repository import SprintRepository

    sprint = await SprintRepository(session).get_by_id(sprint_id)
    if sprint is None:
        raise HTTPException(status_code=404, detail="Sprint not found.")
    await ensure_project_access(session, principal, sprint.project_id)
    svc = BurndownService(session)
    chart = await svc.get_chart(sprint_id)
    if chart.entries:
        return chart

    live_chart = await TrelloLiveProjectService(session).build_burndown_chart(sprint_id)
    if live_chart is not None:
        return live_chart
    return chart


@router.post("/{sprint_id}/burndown/refresh")
async def refresh_burndown(
    sprint_id: int,
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
):
    from app.services.burndown_service import BurndownService
    from app.repositories.sprint_repository import SprintRepository

    sprint = await SprintRepository(session).get_by_id(sprint_id)
    if sprint is None:
        raise HTTPException(status_code=404, detail="Sprint not found.")
    await ensure_project_access(session, principal, sprint.project_id)
    svc = BurndownService(session)
    return await svc.refresh_burndown(sprint_id)

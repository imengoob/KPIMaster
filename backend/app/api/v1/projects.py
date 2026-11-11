from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.authz import AuthPrincipal, CurrentPrincipal, ensure_project_access, list_accessible_project_ids, require_roles
from app.api.dependencies import DbSession, ProjectRepo
from app.models.company import CompanyProjectAccess
from app.models.project import Project
from app.schemas.common import PaginatedResponse
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["Projects"])


def _as_date(value: str | None):
    if not value:
        return None
    from dateutil.parser import parse as parse_date

    parsed = parse_date(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC)
    return parsed.date()


@router.get("", response_model=PaginatedResponse[ProjectResponse])
async def list_projects(
    repo: ProjectRepo,
    session: DbSession,
    principal: CurrentPrincipal,
    active_only: bool = Query(True),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> PaginatedResponse[ProjectResponse]:
    offset = (page - 1) * page_size
    accessible_ids = await list_accessible_project_ids(session, principal)
    accessible_set = None if accessible_ids is None else set(accessible_ids)
    if active_only:
        items = await repo.get_all_active()
        if accessible_set is not None:
            items = [project for project in items if project.id in accessible_set]
        total = len(items)
        items = items[offset : offset + page_size]
    else:
        items = await repo.get_all(offset=0, limit=1000)
        if accessible_set is not None:
            items = [project for project in items if project.id in accessible_set]
        total = len(items)
        items = items[offset : offset + page_size]

    return PaginatedResponse(
        items=[ProjectResponse.model_validate(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    body: ProjectCreate,
    repo: ProjectRepo,
    session: DbSession,
    principal: AuthPrincipal = Depends(require_roles("super_admin", "company_admin", "client_admin", "esn_admin")),
) -> ProjectResponse:
    existing = await repo.get_by_key(body.key)
    if existing:
        raise HTTPException(status_code=409, detail=f"Project key '{body.key}' already exists.")

    project = Project(**body.model_dump())
    project = await repo.create(project)
    if principal.company_id is not None and not principal.is_superuser:
        session.add(CompanyProjectAccess(company_id=principal.company_id, project_id=project.id))
        await session.flush()
    return ProjectResponse.model_validate(project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: int, repo: ProjectRepo, session: DbSession, principal: CurrentPrincipal) -> ProjectResponse:
    await ensure_project_access(session, principal, project_id)
    project = await repo.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return ProjectResponse.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    body: ProjectUpdate,
    repo: ProjectRepo,
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
) -> ProjectResponse:
    await ensure_project_access(session, principal, project_id)
    project = await repo.get_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    update_data = body.model_dump(exclude_unset=True)
    project = await repo.update(project, **update_data)
    return ProjectResponse.model_validate(project)


@router.get("/{project_id}/sprints/current")
async def get_current_sprint(
    project_id: int,
    session: DbSession,
    principal: CurrentPrincipal,
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
):
    """Returns the currently active sprint for a project."""
    from app.repositories.sprint_repository import SprintRepository
    from app.schemas.sprint import SprintResponse
    from app.services.trello.live_project_service import TrelloLiveProjectService

    await ensure_project_access(session, principal, project_id)
    repo = SprintRepository(session)
    range_start = _as_date(start_date)
    range_end = _as_date(end_date)
    sprint = (
        await repo.get_sprint_for_range(project_id, start_date=range_start, end_date=range_end)
        if range_start is not None or range_end is not None
        else await repo.get_active_sprint(project_id)
    )
    if sprint:
        return SprintResponse.model_validate(sprint)

    live_service = TrelloLiveProjectService(session)
    board_info = await live_service.get_primary_board(project_id)
    if not board_info:
        raise HTTPException(status_code=404, detail="No active sprint found for this project.")

    board, _ = board_info
    sprint = await live_service.ensure_live_sprint(project_id, board)
    return SprintResponse.model_validate(sprint)


@router.get("/{project_id}/sprints")
async def list_project_sprints(project_id: int, session: DbSession, principal: CurrentPrincipal):
    from app.repositories.sprint_repository import SprintRepository
    from app.schemas.sprint import SprintResponse

    await ensure_project_access(session, principal, project_id)
    repo = SprintRepository(session)
    sprints = await repo.get_sprints_for_project(project_id)
    return [SprintResponse.model_validate(s) for s in sprints]


@router.get("/{project_id}/sprints/velocity")
async def get_velocity_history(
    project_id: int,
    session: DbSession,
    principal: CurrentPrincipal,
    limit: int = Query(5, ge=1, le=20),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
):
    """Returns sprint velocity history — used by the velocity trend chart."""
    from app.repositories.sprint_repository import SprintRepository
    from app.services.trello.live_project_service import TrelloLiveProjectService

    await ensure_project_access(session, principal, project_id)
    repo = SprintRepository(session)
    completed = await repo.get_completed_sprints(
        project_id,
        limit=limit,
        start_date=_as_date(start_date),
        end_date=_as_date(end_date),
    )
    if not completed:
        live_series = await TrelloLiveProjectService(session).velocity_history(project_id, start_date, end_date)
        if live_series:
            return live_series[:limit]

    # Return oldest → newest so the chart renders left-to-right
    return [
        {"sprint": s.name, "points": s.velocity or s.completed_points}
        for s in reversed(completed)
    ]

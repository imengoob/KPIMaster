from fastapi import APIRouter, Depends, Query

from app.api.authz import AuthPrincipal, CurrentPrincipal, ensure_project_access, require_roles
from app.api.dependencies import DbSession
from app.schemas.repository_activity import RepositoryMismatchResponse

router = APIRouter(prefix="/repository-mismatches", tags=["Repository"])


@router.get("", response_model=list[RepositoryMismatchResponse])
async def list_mismatches(
    session: DbSession,
    principal: CurrentPrincipal,
    project_id: int = Query(..., description="Project ID to scan"),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    provider: str | None = Query(None),
) -> list[RepositoryMismatchResponse]:
    """
    Returns all detected mismatches between ticket status and git activity.
    Matches the frontend BackendRepositoryMismatch interface field-for-field.
    """
    await ensure_project_access(session, principal, project_id)
    from app.services.repository_analyzer_service import RepositoryAnalyzerService
    from app.services.trello.live_project_service import TrelloLiveProjectService

    svc = RepositoryAnalyzerService(session)
    if provider in {"jira", "microsoft"}:
        return []

    if provider == "trello":
        live_mismatches = await TrelloLiveProjectService(session).list_repo_mismatches(
            project_id,
            start_date=start_date,
            end_date=end_date,
        )
        return live_mismatches

    mismatches = await svc.get_mismatches(
        project_id,
        start_date=start_date,
        end_date=end_date,
        provider=provider,
    )
    if provider == "github":
        return [RepositoryMismatchResponse.model_validate(m) for m in mismatches]
    if not mismatches:
        live_mismatches = await TrelloLiveProjectService(session).list_repo_mismatches(
            project_id,
            start_date=start_date,
            end_date=end_date,
        )
        if live_mismatches:
            return live_mismatches
    return [RepositoryMismatchResponse.model_validate(m) for m in mismatches]


@router.post("/scan", summary="Trigger repository scan for a project")
async def trigger_scan(
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
) -> dict:
    from app.services.repository_analyzer_service import RepositoryAnalyzerService

    await ensure_project_access(session, principal, project_id)
    svc = RepositoryAnalyzerService(session)
    return await svc.scan_project(project_id)

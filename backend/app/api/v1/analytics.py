from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException

from app.api.authz import AuthPrincipal, CurrentPrincipal, ensure_project_access, get_allowed_kpi_subject_ids, require_roles
from app.api.dependencies import DbSession
from app.schemas.responsiveness import ResponsivenessMetrics
from app.services.analytics.responsiveness_service import ResponsivenessAnalyticsService
from app.services.developer_kpi_service import DeveloperKPIService
from app.schemas.developer import ClientProgressReport, DeveloperKPIReport
from app.models.developer import Developer
from sqlalchemy import select

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/responsiveness", response_model=ResponsivenessMetrics)
async def get_responsiveness(
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
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    provider: str | None = Query(None),
) -> ResponsivenessMetrics:
    """Get developer responsiveness analytics for a specific project."""
    await ensure_project_access(session, principal, project_id)

    # Restrict to developers that this principal is allowed to see.
    allowed_ids = await get_allowed_kpi_subject_ids(session, principal, project_id)

    svc = ResponsivenessAnalyticsService(session)
    try:
        report = await svc.compute_responsiveness_metrics(
            project_id=project_id,
            allowed_developer_ids=allowed_ids,
            start_date=start_date,
            end_date=end_date,
            provider=provider,
        )
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vendor/developers", response_model=ClientProgressReport)
async def get_vendor_developers(
    session: DbSession,
    principal: AuthPrincipal = Depends(
        require_roles("super_admin", "esn_admin", "esn_delivery_manager")
    ),
    project_id: int = Query(...),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    provider: str | None = Query(None),
) -> ClientProgressReport:
    """Get aggregated developer KPIs for a Vendor (ESN) across the specified project."""
    await ensure_project_access(session, principal, project_id)

    # Restrict to developers that this principal is allowed to see
    allowed_ids = await get_allowed_kpi_subject_ids(session, principal, project_id)
    from app.schemas.developer import ClientProgressReport, ClientProgressSummary
    from datetime import datetime, timezone

    if not allowed_ids:
        # Return empty report
        return ClientProgressReport(
            project_id=project_id,
            sprint_id=None,
            summary=ClientProgressSummary(
                total_developers=0,
                on_track_count=0,
                at_risk_count=0,
                behind_count=0,
                story_points_completed=0,
                story_points_total=0,
                active_blockers=0,
                overall_completion_rate=0.0,
                avg_cycle_time_hours=0.0,
                last_updated_at=datetime.now(timezone.utc).isoformat(),
            ),
            members=[],
            computed_at=datetime.now(timezone.utc).isoformat()
        )

    svc = DeveloperKPIService(session)
    report = await svc.compute_client_progress(
        project_id,
        None,
        start_date=start_date,
        end_date=end_date,
        provider=provider,
    )

    # Filter developers by allowed_ids
    filtered = [d for d in report.members if d.developer_id in allowed_ids]
    report.members = filtered

    from app.api.v1.developers import _recompute_client_progress_summary
    _recompute_client_progress_summary(report)

    return report

@router.get("/developer/me", response_model=DeveloperKPIReport)
async def get_developer_me(
    session: DbSession,
    principal: AuthPrincipal = Depends(require_roles("developer")),
    project_id: int = Query(...),
    sprint_id: int | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    provider: str | None = Query(None),
) -> DeveloperKPIReport:
    """Get personal developer KPIs for the logged-in developer on a specified project."""
    await ensure_project_access(session, principal, project_id)

    result = await session.execute(
        select(Developer).where(Developer.user_id == principal.user.id)
    )
    developer = result.scalar_one_or_none()
    if not developer:
        raise HTTPException(status_code=404, detail="Developer profile not found")

    svc = DeveloperKPIService(session)
    report = await svc.compute_developer_kpis(
        developer_id=developer.id,
        project_id=project_id,
        sprint_id=sprint_id,
        start_date=start_date,
        end_date=end_date,
        provider=provider,
    )
    if not report:
        raise HTTPException(status_code=404, detail="KPI Data not found for this developer.")

    return report

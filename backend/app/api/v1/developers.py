from datetime import date
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select

from app.api.authz import (
    AuthPrincipal,
    CurrentPrincipal,
    ensure_developer_access,
    ensure_engagement_access,
    ensure_kpi_subject_access,
    ensure_project_access,
    get_allowed_kpi_subject_ids,
    require_roles,
)
from app.api.dependencies import DbSession
from app.models.company import Company, CompanyProjectAccess, CompanyPartnership
from app.models.developer import Developer, DeveloperClientVisibility
from app.models.developer_external_identity import DeveloperExternalIdentity
from app.models.engagement import DeveloperAssignment, Engagement
from app.schemas.developer import (
    ClientProgressReport,
    DeveloperCreate,
    DeveloperKPIReport,
    DeveloperProgressReport,
    DeveloperResponse,
    DeveloperUpdate,
    TrelloMemberCandidate,
    TeamKPIReport,
    VendorDeveloperProfileResponse,
    VendorDeveloperProfileUpsert,
    DeveloperVisibilityCreate,
    DeveloperVisibilityResponse,
    DeveloperHistoryEntry,
    DeveloperRecruitingProfile,
    DeveloperSprintKPIResponse,
)
from app.models.developer_sprint_kpi import DeveloperSprintKPI

router = APIRouter(prefix="/developers", tags=["Developers"])
_NON_SLUG = re.compile(r"[^a-z0-9]+")


def _normalize_name(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _slug(value: str) -> str:
    return _NON_SLUG.sub("-", value.strip().casefold()).strip("-") or "developer"


def _candidate_score(search: str, full_name: str, username: str | None) -> float:
    wanted = _normalize_name(search)
    display = _normalize_name(full_name)
    handle = _normalize_name(username or "")
    if wanted == display:
        return 1.0
    if wanted == handle:
        return 0.96
    if wanted and (wanted in display or display in wanted):
        return 0.82
    wanted_tokens = set(wanted.split())
    display_tokens = set(display.split()) | set(handle.split())
    if not wanted_tokens:
        return 0.0
    overlap = len(wanted_tokens & display_tokens) / len(wanted_tokens)
    return round(overlap * 0.75, 2)


async def _unique_developer_username(session: DbSession, full_name: str, company_id: int) -> str:
    base = f"{_slug(full_name)}-{company_id}"[:90]
    candidate = base
    counter = 1
    while await session.scalar(select(Developer.id).where(Developer.username == candidate)):
        counter += 1
        candidate = f"{base[:90]}-{counter}"
    return candidate


async def _unique_developer_email(session: DbSession, full_name: str, company_id: int) -> str:
    base = f"{_slug(full_name)}-{company_id}"
    candidate = f"{base}@vendor.sprintpulse.local"
    counter = 1
    while await session.scalar(select(Developer.id).where(Developer.email == candidate)):
        counter += 1
        candidate = f"{base}-{counter}@vendor.sprintpulse.local"
    return candidate


@router.get("", response_model=list[DeveloperResponse])
async def list_developers(
    session: DbSession,
    principal: CurrentPrincipal,
    active_only: bool = Query(True),
    project_id: int | None = Query(None),
) -> list[DeveloperResponse]:
    from app.services.trello.live_project_service import TrelloLiveProjectService

    stmt = (
        select(Developer)
        .outerjoin(DeveloperAssignment, DeveloperAssignment.developer_id == Developer.id)
        .outerjoin(Engagement, Engagement.id == DeveloperAssignment.engagement_id)
    )
    if active_only:
        stmt = stmt.where(Developer.is_active.is_(True))
    if not principal.is_superuser and not principal.is_solution_owner and principal.company_id is not None:
        company = await session.get(Company, principal.company_id)
        if company and company.tenant_type == "vendor":
            stmt = stmt.where(Developer.company_id == principal.company_id)
        else:
            stmt = stmt.outerjoin(CompanyProjectAccess, CompanyProjectAccess.project_id == Engagement.project_id).where(
                or_(
                    Developer.company_id == principal.company_id,
                    Engagement.client_company_id == principal.company_id,
                    Engagement.vendor_company_id == principal.company_id,
                    CompanyProjectAccess.company_id == principal.company_id,
                )
            )
    stmt = stmt.order_by(Developer.name)
    result = await session.execute(stmt)
    devs = list(result.scalars().unique().all())
    if project_id is not None:
        await ensure_project_access(session, principal, project_id)
        live_devs = await TrelloLiveProjectService(session).list_developers(project_id)
        if live_devs:
            allowed_ids = await get_allowed_kpi_subject_ids(session, principal, project_id)
            if allowed_ids is not None:
                live_devs = [dev for dev in live_devs if dev.id in allowed_ids]
            return live_devs
    if principal.role == "developer" and principal.developer_id is not None:
        devs = [dev for dev in devs if dev.id == principal.developer_id]
    return [DeveloperResponse.model_validate(d) for d in devs]


@router.post("", response_model=DeveloperResponse, status_code=201)
async def create_developer(
    body: DeveloperCreate,
    session: DbSession,
    principal: AuthPrincipal = Depends(require_roles("super_admin", "company_admin", "client_admin", "esn_admin")),
) -> DeveloperResponse:
    # Check uniqueness
    existing = await session.execute(
        select(Developer).where(Developer.email == body.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already in use.")

    payload = body.model_dump()
    if not principal.is_superuser:
        payload["company_id"] = principal.company_id
    dev = Developer(**payload)
    session.add(dev)
    await session.flush()
    await session.refresh(dev)
    return DeveloperResponse.model_validate(dev)


@router.get("/trello-member-candidates", response_model=list[TrelloMemberCandidate])
async def list_trello_member_candidates(
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
    project_id: int = Query(...),
    full_name: str = Query(..., min_length=2),
) -> list[TrelloMemberCandidate]:
    """Return Trello board members ranked against a vendor-entered full name."""
    await ensure_project_access(session, principal, project_id)
    members = await _fetch_project_trello_members(session, project_id)
    if not members:
        return []

    identity_rows = await session.execute(
        select(DeveloperExternalIdentity.external_user_id, DeveloperExternalIdentity.developer_id)
        .where(
            DeveloperExternalIdentity.provider == "trello",
            DeveloperExternalIdentity.is_active.is_(True),
        )
    )
    linked = {external_id: developer_id for external_id, developer_id in identity_rows.all()}

    candidates = [
        TrelloMemberCandidate(
            trello_member_id=member_id,
            full_name=name,
            username=username,
            match_score=_candidate_score(full_name, name, username),
            already_linked_developer_id=linked.get(member_id),
        )
        for member_id, name, username in members
    ]
    return [
        candidate
        for candidate in sorted(candidates, key=lambda item: item.match_score, reverse=True)
        if candidate.match_score >= 0.35
    ][:8]


@router.post("/vendor-profile", response_model=VendorDeveloperProfileResponse, status_code=201)
async def upsert_vendor_developer_profile(
    body: VendorDeveloperProfileUpsert,
    session: DbSession,
    principal: AuthPrincipal = Depends(
        require_roles("super_admin", "esn_admin", "esn_delivery_manager", "client_admin", "client_pm")
    ),
) -> VendorDeveloperProfileResponse:
    """
    Create/update a vendor-owned developer, assign them to an engagement, and
    optionally link their Trello member identity.
    """
    engagement = await ensure_engagement_access(session, principal, body.engagement_id)
    if not principal.is_superuser and not principal.is_solution_owner:
        if principal.company_id not in (engagement.vendor_company_id, engagement.client_company_id):
            raise HTTPException(status_code=403, detail="Only authorized vendor or client administrators can manage this roster.")

    developer = await _find_or_create_vendor_developer(session, engagement.vendor_company_id, body)
    assignment = await _ensure_developer_assignment(session, engagement, developer, body)

    match_source = "none"
    matched_member_id = body.trello_member_id
    matched_member_name: str | None = None
    if not matched_member_id:
        exact = await _find_exact_trello_member_by_name(session, engagement.project_id, body.full_name)
        if exact is not None:
            matched_member_id, matched_member_name, _ = exact
            match_source = "exact_name"
    else:
        matched_member_name = await _lookup_trello_member_name(session, engagement.project_id, matched_member_id)
        match_source = "confirmed"

    if matched_member_id:
        await _upsert_trello_identity(session, developer, matched_member_id, matched_member_name)
        developer.trello_member_id = matched_member_id
        session.add(developer)

    await session.flush()
    await session.refresh(developer)
    await session.refresh(assignment, attribute_names=["developer", "engagement"])
    return VendorDeveloperProfileResponse(
        developer=DeveloperResponse.model_validate(developer),
        engagement_id=engagement.id,
        assignment_id=assignment.id,
        matched_trello_member_id=matched_member_id,
        matched_trello_member_name=matched_member_name,
        match_source=match_source,
    )


@router.get("/team-kpis", response_model=TeamKPIReport)
async def get_team_kpis(
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
    sprint_id: int | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    provider: str | None = Query(None),
) -> TeamKPIReport:
    """Team KPI matrix — one row per active developer with aggregates and warning signals."""
    from app.services.developer_kpi_service import DeveloperKPIService
    await ensure_project_access(session, principal, project_id)
    report = await DeveloperKPIService(session).compute_team_kpis(
        project_id,
        sprint_id,
        start_date=start_date,
        end_date=end_date,
        provider=provider,
    )
    allowed_ids = await get_allowed_kpi_subject_ids(session, principal, project_id)
    if allowed_ids is not None:
        report.members = [member for member in report.members if member.developer_id in allowed_ids]
        report.warning_signals = [
            signal for signal in report.warning_signals if signal.developer_id in allowed_ids
        ]
        _recompute_team_report_summary(report)
    return report


@router.get("/client-progress", response_model=ClientProgressReport)
async def get_client_progress(
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
    sprint_id: int | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    provider: str | None = Query(None),
) -> ClientProgressReport:
    """Client-facing delivery snapshot for the selected project."""
    from app.services.developer_kpi_service import DeveloperKPIService
    await ensure_project_access(session, principal, project_id)
    report = await DeveloperKPIService(session).compute_client_progress(
        project_id,
        sprint_id,
        start_date=start_date,
        end_date=end_date,
        provider=provider,
    )
    allowed_ids = await get_allowed_kpi_subject_ids(session, principal, project_id)
    if allowed_ids is not None:
        report.members = [member for member in report.members if member.developer_id in allowed_ids]
        _recompute_client_progress_summary(report)
    return report


@router.get("/{developer_id}/kpis", response_model=DeveloperKPIReport)
async def get_developer_kpis(
    developer_id: int,
    session: DbSession,
    principal: CurrentPrincipal,
    project_id: int = Query(...),
    sprint_id: int | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    provider: str | None = Query(None),
) -> DeveloperKPIReport:
    """Full KPI report for one developer: cycle time, blockers, task-type profile, QRT, UQR."""
    from app.services.developer_kpi_service import DeveloperKPIService
    await ensure_project_access(session, principal, project_id)
    await ensure_kpi_subject_access(session, principal, developer_id, project_id)
    try:
        return await DeveloperKPIService(session).compute_developer_kpis(
            developer_id,
            project_id,
            sprint_id,
            start_date=start_date,
            end_date=end_date,
            provider=provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{developer_id}", response_model=DeveloperResponse)
async def get_developer(
    developer_id: int,
    session: DbSession,
    principal: CurrentPrincipal,
) -> DeveloperResponse:
    await ensure_developer_access(session, principal, developer_id)
    result = await session.execute(
        select(Developer).where(Developer.id == developer_id)
    )
    dev = result.scalar_one_or_none()
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found.")
    return DeveloperResponse.model_validate(dev)


@router.patch("/{developer_id}", response_model=DeveloperResponse)
async def update_developer(
    developer_id: int,
    body: DeveloperUpdate,
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
            "developer",
        )
    ),
) -> DeveloperResponse:
    await ensure_developer_access(session, principal, developer_id)
    result = await session.execute(
        select(Developer).where(Developer.id == developer_id)
    )
    dev = result.scalar_one_or_none()
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found.")

    for key, value in body.model_dump(exclude_unset=True).items():
        if key == "company_id" and not principal.is_superuser:
            continue
        setattr(dev, key, value)
    session.add(dev)
    await session.flush()
    await session.refresh(dev)
    return DeveloperResponse.model_validate(dev)


@router.get("/{developer_id}/progress/{sprint_id}", response_model=DeveloperProgressReport)
async def get_developer_progress(
    developer_id: int,
    sprint_id: int,
    session: DbSession,
    principal: CurrentPrincipal,
) -> DeveloperProgressReport:
    """
    Computes per-developer progress within a sprint:
    assigned, completed, in-progress, blocked, and estimation accuracy.
    """
    from sqlalchemy import and_, select
    from app.models.ticket import Ticket
    from app.domain.value_objects.ticket_status import TicketStatus

    await ensure_developer_access(session, principal, developer_id)
    result = await session.execute(
        select(Developer).where(Developer.id == developer_id)
    )
    dev = result.scalar_one_or_none()
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found.")

    tickets_result = await session.execute(
        select(Ticket).where(
            and_(
                Ticket.sprint_id == sprint_id,
                Ticket.assignee_id == developer_id,
            )
        )
    )
    tickets = list(tickets_result.scalars().all())

    completed = [t for t in tickets if t.status == TicketStatus.DONE.value]
    in_progress = [t for t in tickets if t.status == TicketStatus.IN_PROGRESS.value]
    blocked = [t for t in tickets if t.status == TicketStatus.BLOCKED.value]

    total_est = sum(t.estimated_hours or 0 for t in tickets)
    total_actual = sum(t.actual_hours or 0 for t in completed)

    # Estimation accuracy
    errors = []
    for t in completed:
        if t.estimated_hours and t.actual_hours and t.estimated_hours > 0:
            errors.append(abs(t.actual_hours - t.estimated_hours) / t.estimated_hours)
    accuracy = round(1 - (sum(errors) / len(errors)), 4) if errors else 1.0

    on_track = bool(tickets) and len(blocked) == 0 and (
        len(in_progress) > 0 or len(completed) == len(tickets)
    )

    return DeveloperProgressReport(
        developer_id=developer_id,
        developer_name=dev.name,
        assigned_tickets=len(tickets),
        completed_tickets=len(completed),
        in_progress_tickets=len(in_progress),
        blocked_tickets=len(blocked),
        total_estimated_hours=total_est,
        total_actual_hours=total_actual,
        estimation_accuracy=accuracy,
        on_track=on_track,
    )


async def _fetch_project_trello_members(
    session: DbSession,
    project_id: int,
) -> list[tuple[str, str, str | None]]:
    from app.config import settings
    from app.services.trello.client import TrelloClient
    from app.services.trello.live_project_service import TrelloLiveProjectService

    board_info = await TrelloLiveProjectService(session).get_primary_board(project_id)
    if board_info is None:
        return []
    board, credential = board_info
    try:
        async with TrelloClient(
            api_key=credential.api_key,
            api_token=credential.api_token,
            redis_url=settings.redis_url,
        ) as client:
            members = await client.get_board_members(board.trello_id)
    except Exception:
        return []

    return [
        (
            member.id,
            member.fullName or member.username or member.id,
            member.username,
        )
        for member in members
        if member.id
    ]


async def _find_exact_trello_member_by_name(
    session: DbSession,
    project_id: int,
    full_name: str,
) -> tuple[str, str, str | None] | None:
    wanted = _normalize_name(full_name)
    for member_id, name, username in await _fetch_project_trello_members(session, project_id):
        if wanted in {_normalize_name(name), _normalize_name(username or "")}:
            return member_id, name, username
    return None


async def _lookup_trello_member_name(
    session: DbSession,
    project_id: int,
    trello_member_id: str,
) -> str | None:
    for member_id, name, _ in await _fetch_project_trello_members(session, project_id):
        if member_id == trello_member_id:
            return name
    return None


async def _find_or_create_vendor_developer(
    session: DbSession,
    vendor_company_id: int,
    body: VendorDeveloperProfileUpsert,
) -> Developer:
    email = body.email.strip().lower() if body.email else None
    developer: Developer | None = None
    if email:
        developer = await session.scalar(
            select(Developer).where(Developer.email == email)
        )
        if developer is not None and developer.company_id != vendor_company_id:
            raise HTTPException(status_code=409, detail="A developer with this email belongs to another company.")

    if developer is None:
        developer = await session.scalar(
            select(Developer).where(
                Developer.company_id == vendor_company_id,
                func.lower(Developer.name) == body.full_name.strip().lower(),
            )
        )

    if developer is None:
        developer = Developer(
            name=body.full_name.strip(),
            email=email or await _unique_developer_email(session, body.full_name, vendor_company_id),
            username=await _unique_developer_username(session, body.full_name, vendor_company_id),
            company_id=vendor_company_id,
            role=body.role,
            team=body.team,
            is_active=True,
        )
        session.add(developer)
        await session.flush()
        await session.refresh(developer)
        return developer

    developer.name = body.full_name.strip()
    if email:
        developer.email = email
    developer.role = body.role
    developer.team = body.team
    developer.is_active = True
    session.add(developer)
    await session.flush()
    return developer


async def _ensure_developer_assignment(
    session: DbSession,
    engagement: Engagement,
    developer: Developer,
    body: VendorDeveloperProfileUpsert,
) -> DeveloperAssignment:
    if developer.company_id != engagement.vendor_company_id:
        raise HTTPException(status_code=422, detail="Only vendor-owned developers can be assigned to this engagement.")
    assignment = await session.scalar(
        select(DeveloperAssignment)
        .where(
            DeveloperAssignment.developer_id == developer.id,
            DeveloperAssignment.engagement_id == engagement.id,
            DeveloperAssignment.status == "active",
        )
        .order_by(DeveloperAssignment.id.desc())
    )
    if assignment is None:
        assignment = DeveloperAssignment(
            developer_id=developer.id,
            engagement_id=engagement.id,
            assignment_role=body.assignment_role,
            status="active",
            allocation_percentage=body.allocation_percentage,
            start_date=body.start_date or date.today(),
            is_primary=True,
        )
        session.add(assignment)
    else:
        assignment.assignment_role = body.assignment_role
        assignment.allocation_percentage = body.allocation_percentage
        assignment.is_primary = True
        session.add(assignment)
    await session.flush()
    await session.refresh(assignment)
    return assignment


async def _upsert_trello_identity(
    session: DbSession,
    developer: Developer,
    trello_member_id: str,
    display_name: str | None,
) -> None:
    existing_for_member = await session.scalar(
        select(DeveloperExternalIdentity)
        .where(
            DeveloperExternalIdentity.provider == "trello",
            DeveloperExternalIdentity.external_user_id == trello_member_id,
            DeveloperExternalIdentity.integration_account_id.is_(None),
            DeveloperExternalIdentity.is_active.is_(True),
        )
    )
    if existing_for_member and existing_for_member.developer_id != developer.id:
        raise HTTPException(status_code=409, detail="This Trello member is already linked to another developer.")

    identity = existing_for_member or await session.scalar(
        select(DeveloperExternalIdentity)
        .where(
            DeveloperExternalIdentity.provider == "trello",
            DeveloperExternalIdentity.developer_id == developer.id,
            DeveloperExternalIdentity.external_user_id == trello_member_id,
            DeveloperExternalIdentity.integration_account_id.is_(None),
        )
    )
    if identity is None:
        identity = DeveloperExternalIdentity(
            developer_id=developer.id,
            provider="trello",
            external_user_id=trello_member_id,
            integration_account_id=None,
        )
    identity.external_display_name = display_name
    identity.is_active = True
    session.add(identity)


def _mean(values: list[float | None]) -> float | None:
    numeric = [value for value in values if value is not None]
    return round(sum(numeric) / len(numeric), 2) if numeric else None


def _mean_rate(values: list[float | None]) -> float | None:
    numeric = [value for value in values if value is not None]
    return round(sum(numeric) / len(numeric), 4) if numeric else None


def _recompute_team_report_summary(report: TeamKPIReport) -> None:
    report.team_avg_cycle_time_hours = _mean([member.avg_cycle_time_hours for member in report.members])
    report.team_completion_rate = _mean_rate([member.completion_rate for member in report.members]) or 0.0
    report.team_blocker_rate = _mean_rate([member.blocker_rate for member in report.members]) or 0.0
    report.team_question_response_time_hours = _mean([
        member.question_response_time_hours for member in report.members
    ])
    report.team_unanswered_question_rate = _mean_rate([
        member.unanswered_question_rate for member in report.members
    ])


def _recompute_client_progress_summary(report: ClientProgressReport) -> None:
    report.summary.total_developers = len(report.members)
    report.summary.on_track_count = sum(1 for member in report.members if member.status == "on-track")
    report.summary.at_risk_count = sum(1 for member in report.members if member.status == "at-risk")
    report.summary.behind_count = sum(1 for member in report.members if member.status == "behind")
    report.summary.story_points_completed = sum(member.story_points_completed for member in report.members)
    report.summary.story_points_total = sum(member.story_points_total for member in report.members)
    report.summary.active_blockers = sum(member.active_blockers for member in report.members)
    total_tickets = sum(member.tickets_total for member in report.members)
    completed_tickets = sum(member.tickets_completed for member in report.members)
    report.summary.overall_completion_rate = round(completed_tickets / total_tickets, 4) if total_tickets else 0.0
    report.summary.avg_cycle_time_hours = _mean([member.avg_cycle_time_hours for member in report.members])

@router.post("/{developer_id}/visibility", response_model=DeveloperVisibilityResponse, status_code=201)
async def grant_developer_visibility(
    developer_id: int,
    body: DeveloperVisibilityCreate,
    session: DbSession,
    principal: AuthPrincipal = Depends(require_roles("super_admin", "esn_admin", "esn_delivery_manager")),
) -> DeveloperVisibilityResponse:
    developer = await session.get(Developer, developer_id)
    if not developer or (developer.company_id != principal.company_id and not principal.is_superuser):
        raise HTTPException(status_code=404, detail="Developer not found or you don't have access.")

    client = await session.get(Company, body.client_company_id)
    if not client or client.tenant_type != "client":
        raise HTTPException(status_code=400, detail="Target company must be a valid client.")

    existing = await session.scalar(
        select(DeveloperClientVisibility).where(
            DeveloperClientVisibility.developer_id == developer_id,
            DeveloperClientVisibility.client_company_id == body.client_company_id
        )
    )
    if existing:
        return DeveloperVisibilityResponse.model_validate(existing)
        
    grant = DeveloperClientVisibility(
        developer_id=developer_id,
        client_company_id=body.client_company_id,
        granted_by_user_id=principal.user_id
    )
    session.add(grant)
    await session.flush()
    await session.refresh(grant)
    return DeveloperVisibilityResponse.model_validate(grant)


@router.get("/recruiting/pool", response_model=list[DeveloperRecruitingProfile])
async def list_recruiting_pool(
    session: DbSession,
    principal: AuthPrincipal = Depends(require_roles("super_admin", "client_admin", "client_exec")),
) -> list[DeveloperRecruitingProfile]:
    if principal.company_id is None:
        raise HTTPException(status_code=404, detail="No client company linked.")
        
    stmt = (
        select(DeveloperClientVisibility, Developer, Company)
        .join(Developer, Developer.id == DeveloperClientVisibility.developer_id)
        .join(Company, Company.id == Developer.company_id)
        .where(
            DeveloperClientVisibility.client_company_id == principal.company_id,
            DeveloperClientVisibility.status == "approved",
            Developer.is_active.is_(True)
        )
    )
    result = await session.execute(stmt)
    rows = result.all()
    
    response = []
    for grant, dev, company in rows:
        dev_data = DeveloperResponse.model_validate(dev)
        response.append(
            DeveloperRecruitingProfile(
                developer=dev_data,
                vendor_company_name=company.name,
                kpis=None
            )
        )
    return response


@router.get("/me/visibility-requests", response_model=list[DeveloperVisibilityResponse])
async def list_visibility_requests(
    session: DbSession,
    principal: AuthPrincipal = Depends(require_roles("developer")),
) -> list[DeveloperVisibilityResponse]:
    stmt = (
        select(DeveloperClientVisibility)
        .where(
            DeveloperClientVisibility.developer_id == principal.developer_id,
            DeveloperClientVisibility.status == "pending_developer_approval"
        )
    )
    result = await session.execute(stmt)
    return [DeveloperVisibilityResponse.model_validate(g) for g in result.scalars().all()]


@router.post("/me/visibility/{grant_id}/approve", response_model=DeveloperVisibilityResponse)
async def approve_visibility_request(
    grant_id: int,
    session: DbSession,
    principal: AuthPrincipal = Depends(require_roles("developer")),
) -> DeveloperVisibilityResponse:
    grant = await session.get(DeveloperClientVisibility, grant_id)
    if not grant or grant.developer_id != principal.developer_id:
        raise HTTPException(status_code=404, detail="Visibility request not found or unauthorized.")
    if grant.status != "pending_developer_approval":
        raise HTTPException(status_code=400, detail="Request is not pending.")
    
    grant.status = "approved"
    await session.flush()
    return DeveloperVisibilityResponse.model_validate(grant)


@router.post("/me/visibility/{grant_id}/reject", status_code=204)
async def reject_visibility_request(
    grant_id: int,
    session: DbSession,
    principal: AuthPrincipal = Depends(require_roles("developer")),
) -> None:
    grant = await session.get(DeveloperClientVisibility, grant_id)
    if not grant or grant.developer_id != principal.developer_id:
        raise HTTPException(status_code=404, detail="Visibility request not found or unauthorized.")
    
    grant.status = "rejected"
    await session.flush()


@router.get("/{developer_id}/client-history", response_model=list[DeveloperHistoryEntry])
async def get_developer_client_history(
    developer_id: int,
    session: DbSession,
    principal: AuthPrincipal = Depends(
        require_roles("super_admin", "developer", "client_admin", "esn_admin", "company_admin", "esn_delivery_manager")
    ),
) -> list[DeveloperHistoryEntry]:
    if principal.role == "developer" and principal.developer_id != developer_id:
        raise HTTPException(status_code=403, detail="Developers can only view their own history.")
        
    stmt = (
        select(DeveloperAssignment, Engagement, Company)
        .join(Engagement, Engagement.id == DeveloperAssignment.engagement_id)
        .join(Company, Company.id == Engagement.client_company_id)
        .where(DeveloperAssignment.developer_id == developer_id)
        .order_by(DeveloperAssignment.start_date.desc())
    )
    result = await session.execute(stmt)
    rows = result.all()
    
    from app.services.developer_kpi_service import DeveloperKPIService
    kpi_svc = DeveloperKPIService(session)
    
    history = []
    for assignment, engagement, client_company in rows:
        kpis = None
        if engagement.project_id:
            try:
                kpis = await kpi_svc.compute_developer_kpis(engagement.project_id, developer_id)
            except Exception as e:
                # Silently fail KPI extraction so it doesn't break history if source is missing.
                kpis = None

        history.append(
            DeveloperHistoryEntry(
                engagement_id=engagement.id,
                engagement_name=engagement.name,
                client_company_name=client_company.name,
                start_date=assignment.start_date,
                end_date=assignment.end_date,
                assignment_role=assignment.assignment_role,
                allocation_percentage=assignment.allocation_percentage,
                kpis=kpis,
            )
        )
    return history


@router.get("/{developer_id}/history", response_model=list[DeveloperSprintKPIResponse])
async def get_developer_kpi_history(
    developer_id: int,
    session: DbSession,
    principal: CurrentPrincipal,
    project_id: int = Query(...),
) -> list[DeveloperSprintKPIResponse]:
    """Get all historical sprint snapshots for a developer on a project."""
    await ensure_project_access(session, principal, project_id)
    await ensure_kpi_subject_access(session, principal, developer_id, project_id)

    result = await session.execute(
        select(DeveloperSprintKPI)
        .where(DeveloperSprintKPI.developer_id == developer_id)
        .where(DeveloperSprintKPI.project_id == project_id)
        .order_by(DeveloperSprintKPI.computed_at.desc())
    )
    snapshots = result.scalars().all()
    # Pydantic will serialize the SQLAlchemy array to JSON response list.
    return snapshots

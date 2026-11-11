from datetime import datetime
from datetime import date
from typing import Literal

from pydantic import Field

from app.schemas.common import OrmBase


class DeveloperCreate(OrmBase):
    name: str = Field(..., min_length=2, max_length=255)
    email: str = Field(..., max_length=320)
    username: str = Field(..., min_length=2, max_length=100)
    company_id: int | None = None
    trello_member_id: str | None = None
    team: str | None = None
    role: str = "developer"
    slack_id: str | None = None
    github_username: str | None = None


class DeveloperUpdate(OrmBase):
    name: str | None = None
    company_id: int | None = None
    trello_member_id: str | None = None
    team: str | None = None
    role: str | None = None
    slack_id: str | None = None
    github_username: str | None = None
    is_active: bool | None = None


class DeveloperResponse(OrmBase):
    id: int
    name: str
    email: str
    username: str
    company_id: int | None
    trello_member_id: str | None
    team: str | None
    role: str
    slack_id: str | None
    github_username: str | None
    skills: list[str] = Field(default_factory=list)
    is_active: bool
    created_at: datetime
    updated_at: datetime

class DeveloperVisibilityCreate(OrmBase):
    client_company_id: int

class DeveloperVisibilityResponse(OrmBase):
    id: int
    developer_id: int
    client_company_id: int
    granted_by_user_id: int | None
    status: str
    created_at: datetime

class DeveloperHistoryEntry(OrmBase):
    engagement_id: int
    engagement_name: str
    client_company_name: str
    start_date: date
    end_date: date | None
    assignment_role: str
    allocation_percentage: int
    kpis: "DeveloperKPIReport | None" = None

class DeveloperRecruitingProfile(OrmBase):
    developer: DeveloperResponse
    vendor_company_name: str
    kpis: "DeveloperKPIReport | None" = None


class TrelloMemberCandidate(OrmBase):
    trello_member_id: str
    full_name: str
    username: str | None = None
    match_score: float
    already_linked_developer_id: int | None = None


class VendorDeveloperProfileUpsert(OrmBase):
    full_name: str = Field(..., min_length=2, max_length=255)
    engagement_id: int
    email: str | None = Field(default=None, max_length=320)
    role: str = Field(default="developer", min_length=2, max_length=50)
    team: str | None = Field(default=None, max_length=100)
    trello_member_id: str | None = Field(default=None, max_length=100)
    assignment_role: str = Field(default="developer", min_length=2, max_length=100)
    allocation_percentage: int = Field(default=100, ge=1, le=100)
    start_date: date | None = None


class VendorDeveloperProfileResponse(OrmBase):
    developer: DeveloperResponse
    engagement_id: int
    assignment_id: int
    matched_trello_member_id: str | None
    matched_trello_member_name: str | None
    match_source: Literal["confirmed", "exact_name", "none"]


class DeveloperProgressReport(OrmBase):
    """Per-developer progress within a sprint."""

    developer_id: int
    developer_name: str
    assigned_tickets: int
    completed_tickets: int
    in_progress_tickets: int
    blocked_tickets: int
    total_estimated_hours: float
    total_actual_hours: float
    estimation_accuracy: float  # 0.0 – 1.0
    on_track: bool


# ── KPI Framework schemas ─────────────────────────────────────────────────────

DevStatus = Literal["on-track", "at-risk", "behind"]
ActivityFreshness = Literal["active", "recent", "stale", "unknown"]


class TaskTypeProfile(OrmBase):
    """Cycle-time and throughput breakdown for one task type."""

    ticket_type: str           # feature | bug | refactor | investigation | task | other
    count_total: int
    count_done: int
    avg_cycle_time_hours: float | None


class DeveloperTicketResponseMetric(OrmBase):
    """Ticket-level communication and blocker timing for one developer."""

    ticket_id: str
    ticket_title: str
    provider: str
    response_time_hours: float | None = None
    unanswered_questions: int = 0
    exceeded_ert: bool | None = None
    blocker_status: str = "clear"
    blocker_duration_hours: float | None = None


class DeveloperKPIReport(OrmBase):
    """Full KPI report for a single developer in a project/sprint context."""

    developer_id: int
    developer_name: str
    developer_role: str
    project_id: int
    sprint_id: int | None
    provider_sources: list[str] = Field(default_factory=list)
    engagement_name: str | None = None
    client_name: str | None = None

    # Task completion efficiency
    completion_rate: float          # 0.0 – 1.0
    avg_cycle_time_hours: float | None
    estimation_accuracy: float      # 0.0 – 1.0
    tickets_total: int
    tickets_done: int
    tickets_in_progress: int
    tickets_blocked: int
    story_points_completed: int
    story_points_total: int

    # Time spent blocked
    blocker_rate: float             # fraction of tickets that had ≥1 blocker
    avg_blocker_age_hours: float | None
    blocker_count: int = 0
    active_blockers: int
    resolved_blockers: int = 0

    # Idle / stalled detection
    stalled_ticket_count: int

    # Task-type performance patterns
    task_type_profile: list[TaskTypeProfile]

    # Collaboration / communication
    question_response_time_hours: float | None
    unanswered_question_rate: float | None   # 0.0 – 1.0
    comment_response_time_hours: float | None = None
    median_comment_response_time_hours: float | None = None
    unanswered_questions_count: int = 0
    average_response_time_per_ticket_hours: float | None = None
    tickets_exceeded_ert: int = 0
    ert_target_hours: float | None = None
    ert_status: Literal["within-target", "exceeded", "not-available"] = "not-available"
    ticket_response_metrics: list[DeveloperTicketResponseMetric] = Field(default_factory=list)

    # Status + manager signals
    status: DevStatus
    warning_signals: list[str]

    computed_at: str


class TeamMemberSummary(OrmBase):
    """One row in the team KPI matrix."""

    developer_id: int
    developer_name: str
    role: str
    provider_sources: list[str] = Field(default_factory=list)
    engagement_name: str | None = None
    client_name: str | None = None
    story_points_completed: int
    story_points_total: int
    completion_rate: float
    avg_cycle_time_hours: float | None
    blocker_rate: float
    active_blockers: int
    question_response_time_hours: float | None
    unanswered_question_rate: float | None
    ert_target_hours: float | None = None
    ert_status: Literal["within-target", "exceeded", "not-available"] = "not-available"
    status: DevStatus
    warning_count: int


class TeamWarningSignal(OrmBase):
    """A manager-facing warning signal linked to a specific developer."""

    developer_id: int
    developer_name: str
    signal_type: str        # silent_stall | blocker_aging | high_uqr | high_blocker_rate
    description: str
    severity: Literal["info", "warning", "critical"]


class TeamKPIReport(OrmBase):
    """Team-level KPI overview returned by GET /developers/team-kpis."""

    project_id: int
    sprint_id: int | None
    members: list[TeamMemberSummary]
    team_avg_cycle_time_hours: float | None
    team_completion_rate: float
    team_blocker_rate: float
    team_question_response_time_hours: float | None
    team_unanswered_question_rate: float | None
    warning_signals: list[TeamWarningSignal]
    computed_at: str


class ClientProgressSummary(OrmBase):
    """Project-level client delivery summary."""

    total_developers: int
    on_track_count: int
    at_risk_count: int
    behind_count: int
    overall_completion_rate: float
    story_points_completed: int
    story_points_total: int
    active_blockers: int
    avg_cycle_time_hours: float | None
    last_updated_at: str


class ClientProgressMember(OrmBase):
    """Client-facing developer delivery row."""

    developer_id: int
    developer_name: str
    role: str
    provider_sources: list[str] = Field(default_factory=list)
    engagement_name: str | None = None
    client_name: str | None = None
    status: DevStatus
    tickets_completed: int
    tickets_total: int
    story_points_completed: int
    story_points_total: int
    active_work_items: int
    active_blockers: int
    avg_cycle_time_hours: float | None
    question_response_time_hours: float | None = None
    ert_target_hours: float | None = None
    ert_status: Literal["within-target", "exceeded", "not-available"] = "not-available"
    latest_activity_at: str | None
    activity_freshness: ActivityFreshness
    risk_note: str | None


class ClientProgressReport(OrmBase):
    """Client-facing delivery dashboard report for one project."""

    project_id: int
    sprint_id: int | None
    summary: ClientProgressSummary
    members: list[ClientProgressMember]
    computed_at: str

class DeveloperSprintKPIResponse(OrmBase):
    id: int
    developer_id: int
    project_id: int
    sprint_id: int | None
    completion_rate: float
    avg_cycle_time_hours: float | None
    estimation_accuracy: float
    tickets_total: int
    tickets_done: int
    story_points_completed: int
    story_points_total: int
    blocker_rate: float
    avg_blocker_age_hours: float | None
    blocker_count: int
    question_response_time_hours: float | None
    unanswered_question_rate: float | None
    computed_at: str

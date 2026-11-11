/**
 * Backend response shapes (snake_case, matching FastAPI Pydantic schemas).
 * These are what the network layer returns verbatim.
 *
 * Frontend UI types live in src/data/mockData.ts (camelCase).
 * Adapters in each service file convert backend → frontend.
 */

// ─── Projects ───────────────────────────────────────────────────────────────

export interface BackendProject {
  id: number;
  name: string;
  key: string;
  description: string | null;
  repository_url: string | null;
  slack_channel: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface BackendImportedTrelloProject {
  project_id: number;
  project_key: string;
  board_id: number;
  board_name: string;
  trello_board_id: string;
  short_url: string | null;
}

export interface BackendAvailableTrelloBoard {
  id: string;
  name: string;
  description: string | null;
  short_url: string | null;
  is_closed: boolean;
  organization_id: string | null;
}

export interface BackendAuthToken {
  access_token: string;
  token_type: string;
  expires_in_seconds: number;
}

export interface BackendAuthUser {
  id: number;
  username: string;
  email: string;
  role:
    | "super_admin"
    | "company_admin"
    | "company_manager"
    | "client_admin"
    | "client_exec"
    | "client_pm"
    | "esn_admin"
    | "esn_delivery_manager"
    | "developer"
    | "auditor_readonly";
  company_id: number | null;
  company_name: string | null;
  company_slug: string | null;
  developer_id: number | null;
  kpi_subject_id: number | null;
  is_active: boolean;
  is_superuser: boolean;
}

export interface BackendCompany {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  contact_email: string | null;
  is_active: boolean;
}

export interface BackendCompanyPartnershipResponse {
  id: number;
  client_company_id: number;
  vendor_company_id: number;
  status: string;
  vendor_company: BackendCompany | null;
  client_company: BackendCompany | null;
}

export interface BackendTrelloSettings {
  has_credentials: boolean;
  api_key: string;
  api_token: string;
  selected_board_ids: string[];
}

export interface BackendBoardListSummaryItem {
  list_id: number;
  name: string;
  list_type: "backlog" | "wip" | "done" | "unknown";
  card_count: number;
  position: number;
}

export interface BackendBoardSummary {
  project_id: number;
  board_id: number;
  board_name: string;
  lists: BackendBoardListSummaryItem[];
  total_cards: number;
  backlog_count: number;
  wip_count: number;
  done_count: number;
  completion_rate: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ─── Sprints ─────────────────────────────────────────────────────────────────

export interface BackendSprint {
  id: number;
  project_id: number;
  name: string;
  goal: string | null;
  start_date: string;   // "YYYY-MM-DD"
  end_date: string;
  status: string;       // "planning"|"active"|"completed"|"cancelled"
  committed_points: number;
  completed_points: number;
  velocity: number;
  created_at: string;
  updated_at: string;
}

// ─── KPIs ────────────────────────────────────────────────────────────────────

export interface BackendKPISnapshot {
  id: number;
  project_id: number;
  sprint_id: number | null;
  cycle_time_hours: number | null;
  lead_time_hours: number | null;
  velocity: number | null;
  completion_rate: number | null;
  estimation_accuracy: number | null;
  throughput: number | null;
  bug_rate: number | null;
  computed_at: string;
}

export interface BackendKPIDashboard {
  project_id: number;
  sprint_id: number | null;
  current_kpis: BackendKPISnapshot | null;
  velocity_trend: number[];
  completion_trend: number[];
  open_blockers: number;
  stalled_tickets: number;
  repo_mismatches: number;
}

// ─── Burndown ────────────────────────────────────────────────────────────────

export interface BackendBurndownEntry {
  id: number;
  sprint_id: number;
  date: string;
  remaining_points: number;
  completed_points: number;
  ideal_remaining: number;
  cumulative_completed: number;
}

export interface BackendBurndownChart {
  sprint_id: number;
  sprint_name: string;
  start_date: string;
  end_date: string;
  committed_points: number;
  entries: BackendBurndownEntry[];
}

// ─── Tickets ─────────────────────────────────────────────────────────────────

export interface BackendTicket {
  id: number;
  project_id: number;
  sprint_id: number | null;
  assignee_id: number | null;
  reporter_id: number | null;
  title: string;
  description: string | null;
  status: string; // "backlog"|"todo"|"in_progress"|"in_review"|"done"|"blocked"|"cancelled"
  priority: string; // "low"|"medium"|"high"|"critical"
  ticket_type: string;
  estimated_hours: number | null;
  actual_hours: number | null;
  story_points: number | null;
  quality_score: number | null;
  last_activity_at: string;
  created_at: string;
  updated_at: string;
}

// ─── Blockers ────────────────────────────────────────────────────────────────

export interface BackendBlocker {
  id: number;
  ticket_id: number;
  description: string | null;
  stall_hours: number;
  escalation_level: 1 | 2 | 3;
  detected_at: string;
  last_escalated_at: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
  // enriched by the API endpoint
  ticket_title?: string;
  ticket_assignee_id?: number | null;
}

// ─── Developers ──────────────────────────────────────────────────────────────

export interface BackendDeveloper {
  id: number;
  name: string;
  email: string;
  username: string;
  company_id: number | null;
  trello_member_id: string | null;
  team: string | null;
  role: string;
  slack_id: string | null;
  github_username: string | null;
  is_active: boolean;
  skills: string[];
  created_at: string;
  updated_at: string;
}

export interface BackendDeveloperVisibilityResponse {
  id: number;
  developer_id: number;
  client_company_id: number;
  granted_by_user_id: number | null;
  created_at: string;
}

export interface BackendDeveloperHistoryEntry {
  engagement_id: number;
  engagement_name: string;
  client_company_name: string;
  start_date: string;
  end_date: string | null;
  assignment_role: string;
  allocation_percentage: number;
}

export interface BackendDeveloperRecruitingProfile {
  developer: BackendDeveloper;
  vendor_company_name: string;
  kpis: BackendDeveloperKPIReport | null;
}

export interface BackendTrelloMemberCandidate {
  trello_member_id: string;
  full_name: string;
  username: string | null;
  match_score: number;
  already_linked_developer_id: number | null;
}

export interface BackendVendorDeveloperProfile {
  developer: BackendDeveloper;
  engagement_id: number;
  assignment_id: number;
  matched_trello_member_id: string | null;
  matched_trello_member_name: string | null;
  match_source: "confirmed" | "exact_name" | "none";
}

export interface BackendEngagement {
  id: number;
  name: string;
  status: string;
  client_company_id: number;
  client_company_name: string;
  vendor_company_id: number;
  vendor_company_name: string;
  project_id: number;
  project_name: string;
  description: string | null;
  starts_on: string | null;
  ends_on: string | null;
  sla_response_hours: number;
  client_visible: boolean;
  created_at: string;
  updated_at: string;
}

// ─── Repository Activity ─────────────────────────────────────────────────────

export interface BackendRepositoryMismatch {
  id: number;
  ticket_id: number;
  project_id: number;
  branch_name: string | null;
  commit_count: number;
  pr_count: number;
  pr_merged: boolean;
  last_commit_at: string | null;
  mismatch_type: string | null;
  mismatch_reason: string | null;
  scanned_at: string | null;
}

// ─── Action Center ──────────────────────────────────────────────────────────

export type BackendActionStatus =
  | "open"
  | "acknowledged"
  | "in_progress"
  | "awaiting_approval"
  | "approved"
  | "rejected"
  | "resolved"
  | "dismissed";

export type BackendActionPriority = "low" | "medium" | "high" | "critical";

export interface BackendActionEvent {
  id: number;
  action_item_id: number;
  actor_user_id: number | null;
  event_type: string;
  previous_status: string | null;
  next_status: string | null;
  note: string | null;
  payload_json: Record<string, unknown>;
  created_at: string;
}

export interface BackendActionItem {
  id: number;
  project_id: number;
  source_type: string;
  source_id: string;
  source_url: string | null;
  title: string;
  description: string | null;
  recommended_action: string;
  priority: BackendActionPriority;
  owner_user_id: number | null;
  owner_role: string | null;
  status: BackendActionStatus;
  approval_required: boolean;
  due_at: string | null;
  resolved_at: string | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface BackendActionItemDetail extends BackendActionItem {
  events: BackendActionEvent[];
}

export interface BackendActionGenerationResult {
  project_id: number;
  generated: number;
  refreshed: number;
  total_open: number;
  action_ids: number[];
}

// ─── Velocity history (convenience endpoint) ─────────────────────────────────

export interface VelocityPoint {
  sprint: string;
  points: number;
}

// ─── UI-facing types (consumed by pages/components) ──────────────────────────

export interface MetricValue {
  value: string | number;
  change: string;
  type: "positive" | "negative" | "neutral";
}

/** Derived dashboard shapes used by page components */
export interface UISprint {
  id: number;
  name: string;
  startDate: string;
  endDate: string;
  daysRemaining: number;
  totalTickets: number;
  completedTickets: number;
  inProgressTickets: number;
  notStartedTickets: number;
  blockedTickets: number;
  velocity: number;
  previousVelocity: number;
  committedPoints: number;
  completedPoints: number;
}

export interface UIKpi {
  cycleTime: MetricValue;
  leadTime: MetricValue;
  estimationAccuracy: MetricValue;
  blockedCount: MetricValue;
  velocity: MetricValue;
  completionRate: MetricValue;
}

export interface UITicket {
  id: string;
  numericId: number;
  title: string;
  assigneeId: number | null;
  status: "completed" | "in-progress" | "not-started" | "blocked" | "overdue";
  priority: "high" | "medium" | "low" | "critical";
  storyPoints: number;
  dueDate: string;
  qualityScore: number;
  labels: string[];
  stalledHours?: number;
}

export interface UIBlocker {
  id: number;
  ticketId: string;
  title: string;
  assigneeId: number | null;
  stalledHours: number;
  escalationLevel: 1 | 2 | 3;
  reason: string;
  impact: string;
  lastActivity: string;
}

export interface UIDeveloper {
  id: number;
  name: string;
  avatar: string;
  role: string;
  completedPoints: number;
  totalPoints: number;
  ticketsCompleted: number;
  ticketsTotal: number;
  avgCycleTime: number;
  estimationAccuracy: number;
  status: "on-track" | "at-risk" | "behind";
  blockers: number;
}

export interface UIRepoActivity {
  ticket: string;
  ticketId: number;
  branch: string;
  commits: number;
  prs: number;
  prStatus: "merged" | "open" | "review" | "none";
  lastCommit: string;
  mismatch: boolean;
  mismatchReason: string | null;
  mismatchType: string | null;
}

export interface BurndownPoint {
  day: string;
  ideal: number;
  actual: number;
}

// ─── Developer KPI Framework ─────────────────────────────────────────────────

export interface BackendTaskTypeProfile {
  ticket_type: string;
  count_total: number;
  count_done: number;
  avg_cycle_time_hours: number | null;
}

export interface BackendDeveloperKPIReport {
  developer_id: number;
  developer_name: string;
  developer_role: string;
  project_id: number;
  sprint_id: number | null;
  provider_sources?: string[];
  engagement_name?: string | null;
  client_name?: string | null;
  completion_rate: number;
  avg_cycle_time_hours: number | null;
  estimation_accuracy: number;
  tickets_total: number;
  tickets_done: number;
  tickets_in_progress: number;
  tickets_blocked: number;
  story_points_completed: number;
  story_points_total: number;
  blocker_rate: number;
  avg_blocker_age_hours: number | null;
  blocker_count?: number;
  active_blockers: number;
  resolved_blockers?: number;
  stalled_ticket_count: number;
  task_type_profile: BackendTaskTypeProfile[];
  question_response_time_hours: number | null;
  unanswered_question_rate: number | null;
  comment_response_time_hours?: number | null;
  median_comment_response_time_hours?: number | null;
  unanswered_questions_count?: number;
  average_response_time_per_ticket_hours?: number | null;
  tickets_exceeded_ert?: number;
  ert_target_hours?: number | null;
  ert_status?: "within-target" | "exceeded" | "not-available";
  ticket_response_metrics?: BackendDeveloperTicketResponseMetric[];
  status: "on-track" | "at-risk" | "behind";
  warning_signals: string[];
  computed_at: string;
}

export interface BackendDeveloperTicketResponseMetric {
  ticket_id: string;
  ticket_title: string;
  provider: string;
  response_time_hours: number | null;
  unanswered_questions: number;
  exceeded_ert: boolean | null;
  blocker_status: string;
  blocker_duration_hours: number | null;
}

export interface BackendTeamMemberSummary {
  developer_id: number;
  developer_name: string;
  role: string;
  provider_sources?: string[];
  engagement_name?: string | null;
  client_name?: string | null;
  story_points_completed: number;
  story_points_total: number;
  completion_rate: number;
  avg_cycle_time_hours: number | null;
  blocker_rate: number;
  active_blockers: number;
  question_response_time_hours: number | null;
  unanswered_question_rate: number | null;
  ert_target_hours?: number | null;
  ert_status?: "within-target" | "exceeded" | "not-available";
  status: "on-track" | "at-risk" | "behind";
  warning_count: number;
}

export interface BackendTeamWarningSignal {
  developer_id: number;
  developer_name: string;
  signal_type: string;
  description: string;
  severity: "info" | "warning" | "critical";
}

export interface BackendTeamKPIReport {
  project_id: number;
  sprint_id: number | null;
  members: BackendTeamMemberSummary[];
  team_avg_cycle_time_hours: number | null;
  team_completion_rate: number;
  team_blocker_rate: number;
  team_question_response_time_hours: number | null;
  team_unanswered_question_rate: number | null;
  warning_signals: BackendTeamWarningSignal[];
  computed_at: string;
}

export interface BackendClientProgressSummary {
  total_developers: number;
  on_track_count: number;
  at_risk_count: number;
  behind_count: number;
  overall_completion_rate: number;
  story_points_completed: number;
  story_points_total: number;
  active_blockers: number;
  avg_cycle_time_hours: number | null;
  last_updated_at: string;
}

export interface BackendClientProgressMember {
  developer_id: number;
  developer_name: string;
  role: string;
  provider_sources?: string[];
  engagement_name?: string | null;
  client_name?: string | null;
  status: "on-track" | "at-risk" | "behind";
  tickets_completed: number;
  tickets_total: number;
  story_points_completed: number;
  story_points_total: number;
  active_work_items: number;
  active_blockers: number;
  avg_cycle_time_hours: number | null;
  question_response_time_hours?: number | null;
  ert_target_hours?: number | null;
  ert_status?: "within-target" | "exceeded" | "not-available";
  latest_activity_at: string | null;
  activity_freshness: "active" | "recent" | "stale" | "unknown";
  risk_note: string | null;
}

export interface BackendClientProgressReport {
  project_id: number;
  sprint_id: number | null;
  summary: BackendClientProgressSummary;
  members: BackendClientProgressMember[];
  computed_at: string;
}

export interface DeveloperSprintKPIResponse {
  id: number;
  developer_id: number;
  project_id: number;
  sprint_id: number | null;
  completion_rate: number;
  avg_cycle_time_hours: number | null;
  estimation_accuracy: number;
  tickets_total: number;
  tickets_done: number;
  story_points_completed: number;
  story_points_total: number;
  blocker_rate: number;
  avg_blocker_age_hours: number | null;
  blocker_count: number;
  question_response_time_hours: number | null;
  unanswered_question_rate: number | null;
  computed_at: string;
}

export type UserRole =
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

export type PersonaFamily =
  | "Admin"
  | "Client"
  | "Vendor"
  | "Developer"
  | "Executive"
  | "Auditor";

export interface AuthToken {
  access_token: string;
  token_type: string;
  expires_in_seconds: number;
}

export interface AuthUser {
  id: number;
  username: string;
  email: string;
  role: UserRole;
  company_id: number | null;
  company_name: string | null;
  company_slug: string | null;
  developer_id: number | null;
  kpi_subject_id: number | null;
  is_active: boolean;
  is_superuser: boolean;
}

export interface Project {
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

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Sprint {
  id: number;
  project_id: number;
  name: string;
  goal: string | null;
  start_date: string;
  end_date: string;
  status: string;
  committed_points: number;
  completed_points: number;
  velocity: number;
}

export interface KpiSnapshot {
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

export interface KpiDashboard {
  project_id: number;
  sprint_id: number | null;
  current_kpis: KpiSnapshot | null;
  velocity_trend: number[];
  completion_trend: number[];
  open_blockers: number;
  stalled_tickets: number;
  repo_mismatches: number;
}

export type TicketStatus =
  | "backlog"
  | "todo"
  | "in_progress"
  | "in_review"
  | "done"
  | "blocked"
  | "cancelled";

export interface Ticket {
  id: number;
  project_id: number;
  sprint_id: number | null;
  assignee_id: number | null;
  reporter_id: number | null;
  title: string;
  description: string | null;
  status: TicketStatus | string;
  priority: "low" | "medium" | "high" | "critical" | string;
  ticket_type: string;
  estimated_hours: number | null;
  actual_hours: number | null;
  story_points: number | null;
  quality_score: number | null;
  last_activity_at: string;
  created_at: string;
  updated_at: string;
}

export interface TicketQualityReport {
  ticket_id: number;
  quality_score: number;
  missing_fields: string[];
  recommendations: string[];
  evaluated_at?: string;
}

export interface Blocker {
  id: number;
  ticket_id: number;
  description: string | null;
  stall_hours: number;
  escalation_level: 1 | 2 | 3;
  detected_at: string;
  last_escalated_at: string | null;
  resolved_at: string | null;
  ticket_title?: string;
  ticket_assignee_id?: number | null;
}

export interface RepositoryMismatch {
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

export interface IntegrationAccount {
  id: number;
  provider: "jira" | "microsoft" | "trello" | "github";
  account_name: string;
  external_account_id: string;
  is_active: boolean;
  last_sync_at: string | null;
  token_expires_at: string | null;
  scopes: string[];
}

export interface Developer {
  id: number;
  name: string;
  email: string;
  username: string;
  company_id: number | null;
  role: string;
  team: string | null;
  github_username: string | null;
  is_active: boolean;
  skills: string[];
}

export interface TeamMemberSummary {
  developer_id: number;
  developer_name: string;
  role: string;
  story_points_completed: number;
  story_points_total: number;
  completion_rate: number;
  avg_cycle_time_hours: number | null;
  active_blockers: number;
  status: "on-track" | "at-risk" | "behind";
  warning_count: number;
}

export interface TeamKpiReport {
  project_id: number;
  sprint_id: number | null;
  members: TeamMemberSummary[];
  team_avg_cycle_time_hours: number | null;
  team_completion_rate: number;
  team_blocker_rate: number;
  warning_signals: Array<{
    developer_id: number;
    developer_name: string;
    signal_type: string;
    description: string;
    severity: "info" | "warning" | "critical";
  }>;
  computed_at: string;
}

export interface ClientProgressReport {
  project_id: number;
  sprint_id: number | null;
  summary: {
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
  };
  members: Array<{
    developer_id: number;
    developer_name: string;
    role: string;
    status: "on-track" | "at-risk" | "behind";
    tickets_completed: number;
    tickets_total: number;
    story_points_completed: number;
    story_points_total: number;
    active_work_items: number;
    active_blockers: number;
    avg_cycle_time_hours: number | null;
    activity_freshness: "active" | "recent" | "stale" | "unknown";
    risk_note: string | null;
  }>;
  computed_at: string;
}

export interface DeveloperKpiReport {
  developer_id: number;
  developer_name: string;
  developer_role: string;
  project_id: number;
  sprint_id: number | null;
  completion_rate: number;
  avg_cycle_time_hours: number | null;
  estimation_accuracy: number;
  tickets_total: number;
  tickets_done: number;
  tickets_in_progress: number;
  tickets_blocked: number;
  story_points_completed: number;
  story_points_total: number;
  active_blockers: number;
  status: "on-track" | "at-risk" | "behind";
  warning_signals: string[];
  computed_at: string;
}

export interface DashboardBundle {
  sprint: Sprint | null;
  kpis: KpiDashboard | null;
  tickets: Ticket[];
  blockers: Blocker[];
  repositoryMismatches: RepositoryMismatch[];
  integrations: IntegrationAccount[];
  teamReport: TeamKpiReport | null;
  clientProgress: ClientProgressReport | null;
  developerReport: DeveloperKpiReport | null;
}

export type AsyncStatus = "idle" | "loading" | "success" | "error";

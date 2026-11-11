import type { Blocker, DashboardBundle, KpiDashboard, RepositoryMismatch, Sprint, Ticket } from "../domain/types";

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "N/A";
  return `${Math.round(value * 100)}%`;
}

export function formatHours(value: number | null | undefined): string {
  if (value === null || value === undefined) return "N/A";
  if (value >= 24) return `${(value / 24).toFixed(1)}d`;
  return `${Math.round(value)}h`;
}

export function ticketStatusLabel(status: Ticket["status"]): string {
  switch (status) {
    case "done":
      return "Done";
    case "in_progress":
      return "In progress";
    case "in_review":
      return "In review";
    case "blocked":
      return "Blocked";
    case "cancelled":
      return "Cancelled";
    case "todo":
      return "To do";
    default:
      return "Backlog";
  }
}

export function sprintCompletion(sprint: Sprint | null): number {
  if (!sprint || sprint.committed_points <= 0) return 0;
  return Math.min(1, sprint.completed_points / sprint.committed_points);
}

export function summarizeDashboard(bundle: DashboardBundle) {
  const kpis: KpiDashboard | null = bundle.kpis;
  const sprint: Sprint | null = bundle.sprint;
  const tickets = bundle.tickets;
  const blockedTickets = tickets.filter((ticket) => ticket.status === "blocked").length;
  const lowQualityTickets = tickets.filter((ticket) => (ticket.quality_score ?? 0) < 60).length;
  const completedTickets = tickets.filter((ticket) => ticket.status === "done").length;

  return {
    sprintName: sprint?.name ?? "No active sprint",
    sprintCompletion: sprintCompletion(sprint),
    completedPoints: sprint?.completed_points ?? 0,
    committedPoints: sprint?.committed_points ?? 0,
    completionRate: formatPercent(kpis?.current_kpis?.completion_rate ?? null),
    velocity: kpis?.current_kpis?.velocity?.toFixed(0) ?? String(sprint?.velocity ?? 0),
    cycleTime: formatHours(kpis?.current_kpis?.cycle_time_hours),
    leadTime: formatHours(kpis?.current_kpis?.lead_time_hours),
    estimationAccuracy: formatPercent(kpis?.current_kpis?.estimation_accuracy),
    openBlockers: bundle.blockers.length || kpis?.open_blockers || blockedTickets,
    blockedTickets,
    lowQualityTickets,
    completedTickets,
    totalTickets: tickets.length,
    repoMismatches: bundle.repositoryMismatches.length || kpis?.repo_mismatches || 0,
    integrations: bundle.integrations.length
  };
}

export function blockerSeverity(blocker: Blocker): "critical" | "warning" | "info" {
  if (blocker.escalation_level >= 3) return "critical";
  if (blocker.escalation_level === 2) return "warning";
  return "info";
}

export function mismatchLabel(mismatch: RepositoryMismatch): string {
  if (mismatch.mismatch_reason) return mismatch.mismatch_reason;
  if (mismatch.mismatch_type) return mismatch.mismatch_type;
  return "Repository and ticket activity need review.";
}

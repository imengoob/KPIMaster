import { apiFetch } from "./config";
import type {
  BackendSprint,
  BackendKPIDashboard,
  BackendBurndownChart,
  VelocityPoint,
  UISprint,
  UIKpi,
  BurndownPoint,
  MetricValue,
  BackendTicket,
} from "./types";

// ─── Transformers ────────────────────────────────────────────────────────────

function daysRemaining(endDate: string): number {
  const end = new Date(endDate);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diff = Math.ceil((end.getTime() - today.getTime()) / 86_400_000);
  return Math.max(0, diff);
}

/** Count tickets by status to build UISprint's ticket summary */
function ticketCounts(tickets: BackendTicket[]) {
  let completedTickets = 0;
  let inProgressTickets = 0;
  let notStartedTickets = 0;
  let blockedTickets = 0;

  for (const t of tickets) {
    switch (t.status) {
      case "done":
        completedTickets++;
        break;
      case "in_progress":
      case "in_review":
        inProgressTickets++;
        break;
      case "blocked":
        blockedTickets++;
        break;
      default:
        notStartedTickets++;
    }
  }
  return { completedTickets, inProgressTickets, notStartedTickets, blockedTickets };
}

export function adaptSprint(
  sprint: BackendSprint,
  tickets: BackendTicket[],
  previousVelocity = 0,
): UISprint {
  const counts = ticketCounts(tickets);
  return {
    id: sprint.id,
    name: sprint.name,
    startDate: sprint.start_date,
    endDate: sprint.end_date,
    daysRemaining: daysRemaining(sprint.end_date),
    totalTickets: tickets.length,
    committedPoints: sprint.committed_points,
    completedPoints: sprint.completed_points,
    velocity: sprint.velocity ?? sprint.completed_points,
    previousVelocity,
    ...counts,
  };
}

function formatHours(hours: number | null | undefined): string {
  if (hours == null) return "N/A";
  const days = hours / 8; // 8-hour work day
  return days >= 1 ? `${days.toFixed(1)}d` : `${hours.toFixed(0)}h`;
}

function pctChange(current: number | null, previous: number | null): MetricValue["change"] {
  if (current == null || previous == null || previous === 0) return "N/A";
  const pct = ((current - previous) / previous) * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(0)}%`;
}

export function adaptKpis(dash: BackendKPIDashboard): UIKpi {
  const k = dash.current_kpis;
  const vTrend = dash.velocity_trend;
  const prevVelocity = vTrend.length >= 2 ? vTrend[vTrend.length - 2] : null;

  return {
    cycleTime: {
      value: formatHours(k?.cycle_time_hours),
      change: k?.cycle_time_hours != null ? pctChange(k.cycle_time_hours, (k.cycle_time_hours || 0) * 1.1) : "N/A",
      type: "neutral",
    },
    leadTime: {
      value: formatHours(k?.lead_time_hours),
      change: "N/A",
      type: "neutral",
    },
    estimationAccuracy: {
      value: k?.estimation_accuracy != null ? `${Math.round(k.estimation_accuracy * 100)}%` : "N/A",
      change: "N/A",
      type: k?.estimation_accuracy != null && k.estimation_accuracy >= 0.75 ? "positive" : "neutral",
    },
    blockedCount: {
      value: dash.open_blockers,
      change: `${dash.stalled_tickets} stalled`,
      type: dash.open_blockers > 0 ? "negative" : "positive",
    },
    velocity: {
      value: k?.velocity?.toFixed(0) ?? "0",
      change: pctChange(k?.velocity ?? null, prevVelocity),
      type:
        prevVelocity != null && (k?.velocity ?? 0) >= prevVelocity
          ? "positive"
          : "negative",
    },
    completionRate: {
      value:
        k?.completion_rate != null ? `${Math.round(k.completion_rate * 100)}%` : "0%",
      change: "N/A",
      type:
        k?.completion_rate != null && k.completion_rate >= 0.7 ? "positive" : "negative",
    },
  };
}

export function adaptBurndown(chart: BackendBurndownChart): BurndownPoint[] {
  return chart.entries.map((e) => ({
    day: e.date,
    ideal: e.ideal_remaining,
    actual: e.remaining_points,
  }));
}

// ─── API calls ───────────────────────────────────────────────────────────────

export const sprintApi = {
  /** GET /api/v1/projects/{id}/sprints/current */
  getCurrent: (projectId: number, sd?: string, ed?: string) => {
    const p = new URLSearchParams();
    if (sd) p.set("start_date", sd);
    if (ed) p.set("end_date", ed);
    return apiFetch<BackendSprint>(`/projects/${projectId}/sprints/current?${p}`);
  },

  /** GET /api/v1/kpis?project_id={id} */
  getKpis: (projectId: number, sd?: string, ed?: string) => {
    const p = new URLSearchParams({ project_id: String(projectId) });
    if (sd) p.set("start_date", sd);
    if (ed) p.set("end_date", ed);
    return apiFetch<BackendKPIDashboard>(`/kpis?${p}`);
  },

  /**
   * Two-step: get current sprint to find sprint_id,
   * then fetch burndown for that sprint.
   */
  getBurndown: async (projectId: number, sd?: string, ed?: string): Promise<BurndownPoint[]> => {
    const p = new URLSearchParams();
    if (sd) p.set("start_date", sd);
    if (ed) p.set("end_date", ed);
    const sprint = await apiFetch<BackendSprint>(`/projects/${projectId}/sprints/current?${p}`);
    const chart = await apiFetch<BackendBurndownChart>(`/sprints/${sprint.id}/burndown`);
    return adaptBurndown(chart);
  },

  /** GET /api/v1/projects/{id}/sprints/velocity */
  getVelocityHistory: (projectId: number, sd?: string, ed?: string) => {
    const p = new URLSearchParams();
    if (sd) p.set("start_date", sd);
    if (ed) p.set("end_date", ed);
    return apiFetch<VelocityPoint[]>(`/projects/${projectId}/sprints/velocity?${p}`);
  },
};

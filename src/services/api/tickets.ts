import { apiFetch } from "./config";
import type { PlatformFilter } from "@/lib/platforms";
import { getProviderParam } from "@/lib/platforms";
import type {
  BackendTicket,
  BackendBlocker,
  PaginatedResponse,
  UITicket,
  UIBlocker,
} from "./types";

// ─── Transformers ────────────────────────────────────────────────────────────

/** Map backend ticket status → UI status */
function mapStatus(s: string): UITicket["status"] {
  switch (s) {
    case "done":
      return "completed";
    case "in_progress":
    case "in_review":
      return "in-progress";
    case "blocked":
      return "blocked";
    case "cancelled":
      return "completed"; // treat cancelled as done for display
    default:
      return "not-started";
  }
}

/** Map backend priority (includes "critical") → UI priority */
function mapPriority(p: string): UITicket["priority"] {
  if (p === "critical") return "critical";
  if (p === "high") return "high";
  if (p === "low") return "low";
  return "medium";
}

function stalledHours(lastActivityAt: string): number | undefined {
  const last = new Date(lastActivityAt);
  const hours = (Date.now() - last.getTime()) / 3_600_000;
  return hours > 24 ? Math.round(hours) : undefined;
}

export function adaptTicket(t: BackendTicket): UITicket {
  return {
    id: `T-${t.id}`,
    numericId: t.id,
    title: t.title,
    assigneeId: t.assignee_id,
    status: mapStatus(t.status),
    priority: mapPriority(t.priority),
    storyPoints: t.story_points ?? 0,
    dueDate: t.updated_at.split("T")[0],
    qualityScore: t.quality_score ?? 0,
    labels: [t.ticket_type],
    stalledHours: stalledHours(t.last_activity_at),
  };
}

export function adaptBlocker(b: BackendBlocker): UIBlocker {
  const detected = new Date(b.detected_at);
  const hoursAgo = Math.round((Date.now() - detected.getTime()) / 3_600_000);

  return {
    id: b.id,
    ticketId: `T-${b.ticket_id}`,
    title: b.ticket_title ?? `Ticket #${b.ticket_id}`,
    assigneeId: b.ticket_assignee_id ?? null,
    stalledHours: Math.round(b.stall_hours),
    escalationLevel: b.escalation_level,
    reason: b.description ?? "No activity detected.",
    impact:
      b.escalation_level >= 3
        ? "Blocking sprint goal delivery"
        : b.escalation_level === 2
          ? "Team delivery at risk"
          : "Individual ticket delayed",
    lastActivity: `${hoursAgo}h ago`,
  };
}

// ─── API calls ───────────────────────────────────────────────────────────────

export const ticketApi = {
  /** GET /api/v1/tickets?project_id={id} — returns paginated list */
  getAll: async (
    projectId: number,
    startDate?: string | null,
    endDate?: string | null,
    platform?: PlatformFilter,
  ): Promise<UITicket[]> => {
    const p = new URLSearchParams({ project_id: String(projectId), page_size: "1000" });
    if (startDate) p.set("start_date", startDate);
    if (endDate) p.set("end_date", endDate);
    const provider = platform ? getProviderParam(platform) : undefined;
    if (provider) p.set("provider", provider);
    const res = await apiFetch<PaginatedResponse<BackendTicket>>(`/tickets?${p}`);
    return res.items.map(adaptTicket);
  },

  /** Returns raw backend tickets for aggregation (sprint summary, etc.) */
  getAllRaw: async (
    projectId: number,
    startDate?: string | null,
    endDate?: string | null,
    platform?: PlatformFilter,
  ): Promise<BackendTicket[]> => {
    const p = new URLSearchParams({ project_id: String(projectId), page_size: "1000" });
    if (startDate) p.set("start_date", startDate);
    if (endDate) p.set("end_date", endDate);
    const provider = platform ? getProviderParam(platform) : undefined;
    if (provider) p.set("provider", provider);
    const res = await apiFetch<PaginatedResponse<BackendTicket>>(`/tickets?${p}`);
    return res.items;
  },

  getById: async (projectId: number, id: number): Promise<UITicket> => {
    const t = await apiFetch<BackendTicket>(`/tickets/${id}`);
    return adaptTicket(t);
  },

  /** GET /api/v1/blockers?project_id={id} */
  getBlockers: async (
    projectId: number,
    startDate?: string | null,
    endDate?: string | null,
    platform?: PlatformFilter,
  ): Promise<UIBlocker[]> => {
    const p = new URLSearchParams({ project_id: String(projectId) });
    if (startDate) p.set("start_date", startDate);
    if (endDate) p.set("end_date", endDate);
    const provider = platform ? getProviderParam(platform) : undefined;
    if (provider) p.set("provider", provider);
    const list = await apiFetch<BackendBlocker[]>(`/blockers?${p}`);
    return list.map(adaptBlocker);
  },

  actionBlocker: async (blockerId: number, type: string): Promise<BackendBlocker> => {
    return apiFetch<BackendBlocker>(`/blockers/${blockerId}/action`, {
      method: "POST",
      body: JSON.stringify({ action_type: type }),
    });
  },
};

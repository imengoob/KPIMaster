import { apiFetch } from "./config";
import type { PlatformFilter } from "@/lib/platforms";
import { getProviderParam } from "@/lib/platforms";
import type {
  BackendClientProgressReport,
  BackendDeveloper,
  BackendDeveloperKPIReport,
  BackendTrelloMemberCandidate, DeveloperSprintKPIResponse,
  BackendRepositoryMismatch,
  BackendTeamKPIReport,
  BackendVendorDeveloperProfile,
  BackendDeveloperVisibilityResponse,
  BackendDeveloperRecruitingProfile,
  BackendDeveloperHistoryEntry,
  UIDeveloper,
  UIRepoActivity,
} from "./types";

// ─── Transformers ────────────────────────────────────────────────────────────

export function adaptDeveloper(d: BackendDeveloper): UIDeveloper {
  // Avatar: initials from name
  const initials = d.name
    .split(" ")
    .map((w) => w[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  return {
    id: d.id,
    name: d.name,
    avatar: initials,
    role: d.role,
    // Progress fields are unknown without per-sprint data — set placeholder
    completedPoints: 0,
    totalPoints: 0,
    ticketsCompleted: 0,
    ticketsTotal: 0,
    avgCycleTime: 0,
    estimationAccuracy: 100,
    status: "on-track",
    blockers: 0,
  };
}

export function adaptRepositoryMismatch(r: BackendRepositoryMismatch): UIRepoActivity {
  let prStatus: UIRepoActivity["prStatus"] = "none";
  if (r.pr_merged) prStatus = "merged";
  else if (r.pr_count > 0) prStatus = r.commit_count > 0 ? "review" : "open";

  const lastCommit = r.last_commit_at
    ? new Date(r.last_commit_at).toLocaleDateString()
    : "Never";

  return {
    ticket: `T-${r.ticket_id}`,
    ticketId: r.ticket_id,
    branch: r.branch_name ?? `feature/${r.ticket_id}`,
    commits: r.commit_count,
    prs: r.pr_count,
    prStatus,
    lastCommit,
    mismatch: r.mismatch_type != null,
    mismatchReason: r.mismatch_reason,
    mismatchType: r.mismatch_type,
  };
}

// ─── API calls ───────────────────────────────────────────────────────────────

export const developerApi = {
  /** GET /api/v1/developers — global list, filtered client-side if needed */
  getAll: async (projectId?: number): Promise<UIDeveloper[]> => {
    const suffix = projectId ? `?project_id=${projectId}` : "";
    const list = await apiFetch<BackendDeveloper[]>(`/developers${suffix}`);
    return list.map(adaptDeveloper);
  },

  /** GET /api/v1/repository-mismatches?project_id={id} */
  getRepositoryMismatches: async (
    projectId: number,
    startDate?: string | null,
    endDate?: string | null,
    platform?: PlatformFilter,
  ): Promise<UIRepoActivity[]> => {
    const params = new URLSearchParams({ project_id: String(projectId) });
    if (startDate) params.set("start_date", startDate);
    if (endDate) params.set("end_date", endDate);
    const provider = platform ? getProviderParam(platform) : undefined;
    if (provider) params.set("provider", provider);
    const list = await apiFetch<BackendRepositoryMismatch[]>(
      `/repository-mismatches?${params.toString()}`,
    );
    return list.map(adaptRepositoryMismatch);
  },

  /** GET /api/v1/developers/team-kpis?project_id={id}[&sprint_id={id}] */
  getTeamKPIs: async (
    projectId: number,
    sprintId?: number,
    startDate?: string | null,
    endDate?: string | null,
    platform?: PlatformFilter,
  ): Promise<BackendTeamKPIReport> => {
    const p = new URLSearchParams({ project_id: String(projectId) });
    if (sprintId !== undefined) p.set("sprint_id", String(sprintId));
    if (startDate) p.set("start_date", startDate);
    if (endDate) p.set("end_date", endDate);
    const provider = platform ? getProviderParam(platform) : undefined;
    if (provider) p.set("provider", provider);
    return apiFetch<BackendTeamKPIReport>(`/developers/team-kpis?${p}`);
  },

  /** GET /api/v1/developers/client-progress?project_id={id}[&sprint_id={id}] */
  getClientProgress: async (
    projectId: number,
    sprintId?: number,
    startDate?: string | null,
    endDate?: string | null,
    platform?: PlatformFilter,
  ): Promise<BackendClientProgressReport> => {
    const p = new URLSearchParams({ project_id: String(projectId) });
    if (sprintId !== undefined) p.set("sprint_id", String(sprintId));
    if (startDate) p.set("start_date", startDate);
    if (endDate) p.set("end_date", endDate);
    const provider = platform ? getProviderParam(platform) : undefined;
    if (provider) p.set("provider", provider);
    return apiFetch<BackendClientProgressReport>(`/developers/client-progress?${p}`);
  },

  /** GET /api/v1/developers/{id}/kpis?project_id={id}[&sprint_id={id}] */
  getDeveloperKPIs: async (
    developerId: number,
    projectId: number,
    sprintId?: number,
    startDate?: string | null,
    endDate?: string | null,
    platform?: PlatformFilter,
  ): Promise<BackendDeveloperKPIReport> => {
    const p = new URLSearchParams({ project_id: String(projectId) });
    if (sprintId !== undefined) p.set("sprint_id", String(sprintId));
    if (startDate) p.set("start_date", startDate);
    if (endDate) p.set("end_date", endDate);
    const provider = platform ? getProviderParam(platform) : undefined;
    if (provider) p.set("provider", provider);
    return apiFetch<BackendDeveloperKPIReport>(`/developers/${developerId}/kpis?${p}`);
  },

  getDeveloperKPIHistory: async (
    developerId: number,
    projectId: number,
  ): Promise<DeveloperSprintKPIResponse[]> => {
    const p = new URLSearchParams({ project_id: String(projectId) });
    return apiFetch<DeveloperSprintKPIResponse[]>(`/developers/${developerId}/history?${p}`);
  },

  findTrelloMemberCandidates: async (
    projectId: number,
    fullName: string,
  ): Promise<BackendTrelloMemberCandidate[]> => {
    const p = new URLSearchParams({ project_id: String(projectId), full_name: fullName });
    return apiFetch<BackendTrelloMemberCandidate[]>(`/developers/trello-member-candidates?${p}`);
  },

  upsertVendorDeveloperProfile: async (input: {
    fullName: string;
    engagementId: number;
    email?: string;
    role?: string;
    team?: string;
    trelloMemberId?: string;
  }): Promise<BackendVendorDeveloperProfile> =>
    apiFetch<BackendVendorDeveloperProfile>("/developers/vendor-profile", {
      method: "POST",
      body: JSON.stringify({
        full_name: input.fullName,
        engagement_id: input.engagementId,
        email: input.email || null,
        role: input.role || "developer",
        team: input.team || null,
        trello_member_id: input.trelloMemberId || null,
      }),
    }),

  getRecruitingPool: async (): Promise<BackendDeveloperRecruitingProfile[]> => {
    return apiFetch<BackendDeveloperRecruitingProfile[]>("/developers/recruiting/pool");
  },

  getClientHistory: async (developerId: number): Promise<BackendDeveloperHistoryEntry[]> => {
    return apiFetch<BackendDeveloperHistoryEntry[]>(`/developers/${developerId}/client-history`);
  },

  grantVisibility: async (developerId: number, clientCompanyId: number): Promise<BackendDeveloperVisibilityResponse> => {
    return apiFetch<BackendDeveloperVisibilityResponse>(`/developers/${developerId}/visibility`, {
      method: "POST",
      body: JSON.stringify({ client_company_id: clientCompanyId })
    });
  },

  getVisibilityRequests: async (): Promise<BackendDeveloperVisibilityResponse[]> => {
    return apiFetch<BackendDeveloperVisibilityResponse[]>("/developers/me/visibility-requests");
  },

  approveVisibilityRequest: async (grantId: number): Promise<BackendDeveloperVisibilityResponse> => {
    return apiFetch<BackendDeveloperVisibilityResponse>(`/developers/me/visibility/${grantId}/approve`, {
      method: "POST",
    });
  },

  rejectVisibilityRequest: async (grantId: number): Promise<void> => {
    return apiFetch<void>(`/developers/me/visibility/${grantId}/reject`, {
      method: "POST",
    });
  },
};

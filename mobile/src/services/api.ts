import { apiClient, ApiClient } from "./apiClient";
import type {
  AuthToken,
  AuthUser,
  Blocker,
  ClientProgressReport,
  Developer,
  DeveloperKpiReport,
  IntegrationAccount,
  KpiDashboard,
  PaginatedResponse,
  Project,
  RepositoryMismatch,
  Sprint,
  TeamKpiReport,
  Ticket,
  TicketQualityReport
} from "../domain/types";

function withParams(path: string, params: Record<string, string | number | boolean | null | undefined>): string {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") q.set(key, String(value));
  });
  const query = q.toString();
  return query ? `${path}?${query}` : path;
}

export function createKpiApi(client: ApiClient = apiClient) {
  return {
    auth: {
      login: (username: string, password: string) =>
        client.request<AuthToken>("/auth/login", {
          method: "POST",
          body: JSON.stringify({ username, password })
        }),
      me: () => client.request<AuthUser>("/auth/me")
    },

    projects: {
      list: async () => {
        const response = await client.request<PaginatedResponse<Project>>("/projects?page_size=100");
        return response.items;
      }
    },

    sprint: {
      current: (projectId: number) => client.request<Sprint>(`/projects/${projectId}/sprints/current`),
      kpis: (projectId: number) => client.request<KpiDashboard>(withParams("/kpis", { project_id: projectId }))
    },

    tickets: {
      list: async (projectId: number) => {
        const response = await client.request<PaginatedResponse<Ticket>>(
          withParams("/tickets", { project_id: projectId, page_size: 1000 })
        );
        return response.items;
      },
      detail: (ticketId: number) => client.request<Ticket>(`/tickets/${ticketId}`),
      quality: (ticketId: number) => client.request<TicketQualityReport>(`/tickets/${ticketId}/quality`)
    },

    blockers: {
      list: (projectId: number) => client.request<Blocker[]>(withParams("/blockers", { project_id: projectId })),
      action: (blockerId: number, actionType: string) =>
        client.request<Blocker>(`/blockers/${blockerId}/action`, {
          method: "POST",
          body: JSON.stringify({ action_type: actionType })
        }),
      resolve: (blockerId: number) =>
        client.request<Blocker>(`/blockers/${blockerId}/resolve`, {
          method: "POST"
        })
    },

    developers: {
      list: (projectId: number) => client.request<Developer[]>(withParams("/developers", { project_id: projectId })),
      teamKpis: (projectId: number) =>
        client.request<TeamKpiReport>(withParams("/developers/team-kpis", { project_id: projectId })),
      clientProgress: (projectId: number) =>
        client.request<ClientProgressReport>(withParams("/developers/client-progress", { project_id: projectId })),
      developerMe: (projectId: number) =>
        client.request<DeveloperKpiReport>(withParams("/analytics/developer/me", { project_id: projectId }))
    },

    repository: {
      mismatches: (projectId: number) =>
        client.request<RepositoryMismatch[]>(withParams("/repository-mismatches", { project_id: projectId }))
    },

    integrations: {
      list: () => client.request<IntegrationAccount[]>("/integrations")
    }
  };
}

export const kpiApi = createKpiApi();

import { apiFetch, API_V1, AUTH_TOKEN_STORAGE_KEY } from "./config";
import type { BackendImportedTrelloProject } from "./types";

// ─── Backend response types ────────────────────────────────────────────────

export type ProviderType = "jira" | "microsoft" | "trello" | "github";

export interface IntegrationAccount {
  id:                  number;
  user_id:             number;
  provider:            ProviderType;
  account_name:        string;
  external_account_id: string;
  is_active:           boolean;
  last_sync_at:        string | null;
  token_expires_at:    string | null;
  scopes:              string[];
  extra_data:          Record<string, unknown>;
  created_at:          string;
  updated_at:          string;
}

export interface ProviderHealth {
  account_id:       number;
  provider:         ProviderType;
  account_name:     string;
  is_active:        boolean;
  credentials_ok:   boolean;
  last_sync_at:     string | null;
  token_expires_at: string | null;
}

export interface NormalizedBoard {
  id:        string;
  name:      string;
  provider:  ProviderType;
  url:       string | null;
  is_active: boolean;
  extra:     Record<string, unknown>;
}

export interface NormalizedTask {
  id:           string;
  title:        string;
  status:       string;
  board_id:     string;
  provider:     ProviderType;
  description:  string | null;
  priority:     string | null;
  task_type:    string;
  assignee_ids: string[];
  labels:       string[];
  story_points: number | null;
  due_date:     string | null;
  created_at:   string | null;
  updated_at:   string | null;
}

export interface SyncLog {
  id:           number;
  account_id:   number;
  provider:     ProviderType;
  board_id:     string | null;
  sync_type:    "full" | "incremental" | "webhook";
  status:       "running" | "success" | "failed" | "partial";
  items_synced: number;
  errors_count: number;
  error_detail: string | null;
  started_at:   string | null;
  completed_at: string | null;
}

export interface SyncResult {
  account_id:  number;
  board_id:    string;
  provider:    ProviderType;
  synced:      number;
  incremental: boolean;
}

export interface OAuthInitResponse {
  authorization_url: string;
  state:             string;
  provider:          ProviderType;
}

// ─── API client ────────────────────────────────────────────────────────────

export const integrationApi = {
  /** List all connected accounts for current user */
  listAccounts: (provider?: ProviderType): Promise<IntegrationAccount[]> => {
    const q = provider ? `?provider=${provider}` : "";
    return apiFetch<IntegrationAccount[]>(`/integrations${q}`);
  },

  /** Disconnect (soft-delete) an account */
  disconnect: (accountId: number): Promise<void> =>
    apiFetch<void>(`/integrations/${accountId}`, { method: "DELETE" }),

  /** Validate credentials and get sync health */
  getHealth: (accountId: number): Promise<ProviderHealth> =>
    apiFetch<ProviderHealth>(`/integrations/${accountId}/health`),

  /** List boards/projects/plans for an account */
  listBoards: (accountId: number): Promise<NormalizedBoard[]> =>
    apiFetch<NormalizedBoard[]>(`/integrations/${accountId}/boards`),

  /** List tasks for a board */
  listTasks: (accountId: number, boardId: string): Promise<NormalizedTask[]> =>
    apiFetch<NormalizedTask[]>(`/integrations/${accountId}/tasks?board_id=${encodeURIComponent(boardId)}`),

  /** Trigger manual sync */
  triggerSync: (accountId: number, boardId: string, full = false, projectId?: number): Promise<SyncResult> => {
    const p = new URLSearchParams({ board_id: boardId, full: String(full) });
    if (projectId !== undefined) p.set("project_id", String(projectId));
    return apiFetch<SyncResult>(`/integrations/${accountId}/sync?${p}`, { method: "POST" });
  },

  /** Fetch recent sync logs */
  getSyncLogs: (accountId: number, limit = 10): Promise<SyncLog[]> =>
    apiFetch<SyncLog[]>(`/integrations/${accountId}/sync-logs?limit=${limit}`),

  /** Import/link one board from a connected account into KPIMaster projects */
  importBoard: (accountId: number, boardId: string): Promise<{ project_id: number; project_key: string; board_id: string; board_name: string }> =>
    apiFetch<{ project_id: number; project_key: string; board_id: string; board_name: string }>(
      `/integrations/${accountId}/import-board?board_id=${encodeURIComponent(boardId)}`,
      { method: "POST" },
    ),

  /** Connect Trello via API key + token */
  connectTrello: (apiKey: string, apiToken: string, label?: string): Promise<IntegrationAccount> =>
    apiFetch<IntegrationAccount>("/integrations/connect/trello", {
      method:  "POST",
      body:    JSON.stringify({ api_key: apiKey, api_token: apiToken, label: label ?? "Trello" }),
    }),

  /** Connect GitHub via personal access token */
  connectGitHub: (accessToken: string, label?: string): Promise<IntegrationAccount> =>
    apiFetch<IntegrationAccount>("/integrations/connect/github", {
      method: "POST",
      body: JSON.stringify({ access_token: accessToken, label: label ?? "GitHub" }),
    }),

  /** Get Jira OAuth authorization URL — frontend opens the returned URL */
  startJiraOAuth: (clientId: string, clientSecret: string): Promise<OAuthInitResponse> => 
    apiFetch<OAuthInitResponse>("/integrations/oauth/jira/start", {
      method: "POST",
      body: JSON.stringify({ client_id: clientId, client_secret: clientSecret }),
    }),

  /** Get Microsoft OAuth authorization URL — frontend opens the returned URL */
  startMicrosoftOAuth: (): Promise<OAuthInitResponse> =>
    apiFetch<OAuthInitResponse>("/integrations/oauth/microsoft/start"),
};

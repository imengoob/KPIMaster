import { apiFetch } from "./config";
import type {
  BackendActionGenerationResult,
  BackendActionItem,
  BackendActionItemDetail,
  BackendActionPriority,
  BackendActionStatus,
} from "./types";

export interface ActionListParams {
  projectId: number;
  status?: BackendActionStatus | "all";
  sourceType?: string;
  owner?: "mine" | "all";
  includeResolved?: boolean;
}

export interface ActionUpdateInput {
  title?: string;
  description?: string | null;
  recommended_action?: string;
  priority?: BackendActionPriority;
  owner_user_id?: number | null;
  owner_role?: string | null;
  status?: BackendActionStatus;
  approval_required?: boolean;
  due_at?: string | null;
  note?: string | null;
}

function listQuery(params: ActionListParams): string {
  const q = new URLSearchParams({ project_id: String(params.projectId) });
  if (params.status && params.status !== "all") q.set("status", params.status);
  if (params.sourceType && params.sourceType !== "all") q.set("source_type", params.sourceType);
  if (params.owner && params.owner !== "all") q.set("owner", params.owner);
  if (params.includeResolved) q.set("include_resolved", "true");
  return q.toString();
}

export const actionApi = {
  list: (params: ActionListParams): Promise<BackendActionItem[]> =>
    apiFetch<BackendActionItem[]>(`/actions?${listQuery(params)}`),

  get: (id: number): Promise<BackendActionItemDetail> =>
    apiFetch<BackendActionItemDetail>(`/actions/${id}`),

  generate: (projectId: number): Promise<BackendActionGenerationResult> =>
    apiFetch<BackendActionGenerationResult>(`/actions/generate?project_id=${projectId}`, {
      method: "POST",
    }),

  update: (id: number, input: ActionUpdateInput): Promise<BackendActionItemDetail> =>
    apiFetch<BackendActionItemDetail>(`/actions/${id}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    }),

  transition: (
    id: number,
    transition: "acknowledge" | "approve" | "reject" | "dispatch" | "resolve" | "dismiss",
    note?: string | null,
  ): Promise<BackendActionItemDetail> =>
    apiFetch<BackendActionItemDetail>(`/actions/${id}/${transition}`, {
      method: "POST",
      body: JSON.stringify({ note }),
    }),
};


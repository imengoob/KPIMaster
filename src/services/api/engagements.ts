import { apiFetch } from "./config";
import type { BackendEngagement } from "./types";

export interface BackendEngagementAssignment {
  id: number;
  engagement_id: number;
  developer_id: number;
  assignment_role: string;
  status: string;
  allocation_percentage: number;
  start_date: string | null;
  end_date: string | null;
  is_primary?: boolean;
}

export const engagementApi = {
  list: (projectId?: number): Promise<BackendEngagement[]> => {
    const suffix = projectId ? `?project_id=${projectId}` : "";
    return apiFetch<BackendEngagement[]>(`/engagements${suffix}`);
  },
  create: (input: { name: string; status: string; client_company_id?: number; vendor_company_id: number; project_id: number; description?: string; client_visible: boolean }) =>
    apiFetch<BackendEngagement>("/engagements", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  listAssignments: (engagementId: number) =>
    apiFetch<BackendEngagementAssignment[]>(`/engagements/${engagementId}/assignments`),
  createAssignment: (engagementId: number, input: { developer_id: number; assignment_role: string; status: string; allocation_percentage: number }) =>
    apiFetch<BackendEngagementAssignment>(`/engagements/${engagementId}/assignments`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
};

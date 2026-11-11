import { apiFetch } from "./config";
import type { BackendProject, PaginatedResponse } from "./types";

export const projectApi = {
  /** GET /api/v1/projects */
  getAll: async (): Promise<BackendProject[]> => {
    const res = await apiFetch<PaginatedResponse<BackendProject>>(
      `/projects?page_size=100`,
    );
    return res.items;
  },

  /** GET /api/v1/projects/{id} */
  getById: (id: number) => apiFetch<BackendProject>(`/projects/${id}`),
};

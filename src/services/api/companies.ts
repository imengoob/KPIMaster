import { apiFetch } from "./config";
import type { BackendCompany, BackendCompanyPartnershipResponse } from "./types";

export interface UpdateCompanyInput {
  name?: string;
  description?: string;
  contact_email?: string;
}

export const companyApi = {
  getAll: (tenantType?: string) => apiFetch<BackendCompany[]>(`/companies${tenantType ? `?tenant_type=${tenantType}` : ''}`),
  getMine: () => apiFetch<BackendCompany>("/companies/me"),
  updateMine: (input: UpdateCompanyInput) =>
    apiFetch<BackendCompany>("/companies/me", {
      method: "PATCH",
      body: JSON.stringify(input),
    }),
  getPartnerships: () => apiFetch<BackendCompanyPartnershipResponse[]>("/companies/me/partnerships"),
  createPartnership: (vendorCompanyId: number) =>
    apiFetch<BackendCompanyPartnershipResponse>("/companies/me/partnerships", {
      method: "POST",
      body: JSON.stringify({ vendor_company_id: vendorCompanyId }),
    }),
};

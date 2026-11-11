import { apiFetch } from './config';
import type { BackendClientProgressReport, BackendDeveloperKPIReport } from './types';
import type { PlatformFilter } from '@/lib/platforms';
import { getProviderParam } from '@/lib/platforms';

export interface ResponsivenessTrendPoint {
  date_interval: string;
  avg_response_time_hours: number | null;
  avg_reaction_time_hours: number | null;
}

export interface DeveloperResponsivenessRow {
  developer_id: number;
  trello_member_id: string | null;
  developer_name: string;
  total_comments: number;
  total_reactions: number;
  avg_first_reaction_hours: number | null;
  avg_first_response_hours: number | null;
  inactivity_duration_hours: number | null;
  sla_breaching_tickets: number;
}

export interface ResponsivenessMetrics {
  project_id: number | null;
  company_id: number | null;
  global_avg_reaction_hours: number | null;
  global_avg_response_hours: number | null;
  total_developer_comments: number;
  total_developer_reactions: number;
  active_developers: number;
  dormant_developers: number;
  total_sla_breaches: number;
  trend: ResponsivenessTrendPoint[];
  developers: DeveloperResponsivenessRow[];
}

export const analyticsApi = {
  getResponsiveness: async (
    projectId: number,
    startDate?: string | null,
    endDate?: string | null,
    platform?: PlatformFilter,
  ): Promise<ResponsivenessMetrics> => {
    const params = new URLSearchParams({ project_id: String(projectId) });
    if (startDate) params.append("start_date", startDate);
    if (endDate) params.append("end_date", endDate);
    const provider = platform ? getProviderParam(platform) : undefined;
    if (provider) params.append("provider", provider);
    return apiFetch(`/analytics/responsiveness?${params.toString()}`);
  },
  getVendorDevelopers: async (
    projectId: number,
    startDate?: string | null,
    endDate?: string | null,
    platform?: PlatformFilter,
  ): Promise<BackendClientProgressReport> => {
    const params = new URLSearchParams({ project_id: projectId.toString() });
    if (startDate) params.append("start_date", startDate);
    if (endDate) params.append("end_date", endDate);
    const provider = platform ? getProviderParam(platform) : undefined;
    if (provider) params.append("provider", provider);
    return apiFetch(`/analytics/vendor/developers?${params.toString()}`);
  },
  getDeveloperMe: async (
    projectId: number,
    sprintId?: number,
    startDate?: string | null,
    endDate?: string | null,
    platform?: PlatformFilter,
  ): Promise<BackendDeveloperKPIReport> => {
    const params = new URLSearchParams({ project_id: String(projectId) });
    if (sprintId !== undefined) params.append("sprint_id", String(sprintId));
    if (startDate) params.append("start_date", startDate);
    if (endDate) params.append("end_date", endDate);
    const provider = platform ? getProviderParam(platform) : undefined;
    if (provider) params.append("provider", provider);
    return apiFetch(`/analytics/developer/me?${params.toString()}`);
  },
};

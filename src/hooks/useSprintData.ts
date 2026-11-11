import { useQuery } from "@tanstack/react-query";
import { sprintApi, adaptSprint, adaptKpis } from "@/services/api/sprints";
import { ticketApi } from "@/services/api/tickets";
import { developerApi } from "@/services/api/developers";
import type { UISprint } from "@/services/api/types";
import type { PlatformFilter } from "@/lib/platforms";

const STALE_1MIN = 60_000;
const STALE_5MIN = 300_000;

// ─── Sprint + ticket counts composite hook ───────────────────────────────────

export const useCurrentSprint = (projectId: number, sd?: string, ed?: string) => {
  const sprintQ = useQuery({
    queryKey: ["sprint", "current", projectId, sd, ed],
    queryFn: () => sprintApi.getCurrent(projectId, sd, ed),
    staleTime: STALE_5MIN,
    enabled: projectId > 0,
  });

  const ticketsQ = useQuery({
    queryKey: ["tickets", "raw", projectId, sd, ed],
    queryFn: () => ticketApi.getAllRaw(projectId, sd, ed),
    staleTime: STALE_1MIN,
    enabled: projectId > 0,
  });

  let data: UISprint | undefined;
  if (sprintQ.data) {
    data = adaptSprint(sprintQ.data, ticketsQ.data ?? []);
  }

  return {
    data,
    isLoading: sprintQ.isLoading || ticketsQ.isLoading,
    isError: sprintQ.isError || ticketsQ.isError,
    error: sprintQ.error ?? ticketsQ.error,
  };
};

export const useSprintKpis = (projectId: number, sd?: string, ed?: string) =>
  useQuery({
    queryKey: ["kpis", projectId, sd, ed],
    queryFn: () => sprintApi.getKpis(projectId, sd, ed),
    staleTime: STALE_5MIN,
    enabled: projectId > 0,
    select: (dash) => adaptKpis(dash),
  });

export const useBurndown = (projectId: number, sd?: string, ed?: string) =>
  useQuery({
    queryKey: ["burndown", projectId, sd, ed],
    queryFn: () => sprintApi.getBurndown(projectId, sd, ed),
    staleTime: STALE_5MIN,
    enabled: projectId > 0,
  });

export const useVelocityHistory = (projectId: number, sd?: string, ed?: string) =>
  useQuery({
    queryKey: ["velocity", projectId, sd, ed],
    queryFn: () => sprintApi.getVelocityHistory(projectId, sd, ed),
    staleTime: STALE_5MIN,
    enabled: projectId > 0,
  });

export const useTickets = (projectId: number, sd?: string, ed?: string, platform?: PlatformFilter) =>
  useQuery({
    queryKey: ["tickets", projectId, sd, ed, platform],
    queryFn: () => ticketApi.getAll(projectId, sd, ed, platform),
    staleTime: STALE_1MIN,
    enabled: projectId > 0,
  });

export const useBlockers = (projectId: number, sd?: string, ed?: string, platform?: PlatformFilter) =>
  useQuery({
    queryKey: ["blockers", projectId, sd, ed, platform],
    queryFn: () => ticketApi.getBlockers(projectId, sd, ed, platform),
    staleTime: STALE_1MIN,
    enabled: projectId > 0,
  });

export const useDevelopers = (_projectId: number) =>
  useQuery({
    queryKey: ["developers", _projectId],
    queryFn: () => developerApi.getAll(_projectId),
    staleTime: STALE_5MIN,
    enabled: _projectId > 0,
  });

export const useRepositoryMismatches = (projectId: number, sd?: string, ed?: string, platform?: PlatformFilter) =>
  useQuery({
    queryKey: ["repo-mismatches", projectId, sd, ed, platform],
    queryFn: () => developerApi.getRepositoryMismatches(projectId, sd, ed, platform),
    staleTime: STALE_5MIN,
    enabled: projectId > 0,
  });

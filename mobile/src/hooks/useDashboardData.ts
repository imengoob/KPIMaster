import { useCallback, useEffect, useState } from "react";
import type { AuthUser, DashboardBundle } from "../domain/types";
import { isDeveloper, isExecutive } from "../domain/personas";
import { kpiApi } from "../services/api";

interface DashboardState {
  data: DashboardBundle | null;
  isLoading: boolean;
  isRefreshing: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

const emptyBundle: DashboardBundle = {
  sprint: null,
  kpis: null,
  tickets: [],
  blockers: [],
  repositoryMismatches: [],
  integrations: [],
  teamReport: null,
  clientProgress: null,
  developerReport: null
};

async function resolve<T>(promise: Promise<T>): Promise<T | null> {
  try {
    return await promise;
  } catch {
    return null;
  }
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Could not load dashboard data.";
}

export function useDashboardData(projectId: number | null | undefined, user: AuthUser | null, refreshSignal = 0): DashboardState {
  const [data, setData] = useState<DashboardBundle | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (mode: "load" | "refresh" = "load") => {
    if (!projectId || !user) {
      setData(emptyBundle);
      return;
    }

    if (mode === "refresh") setIsRefreshing(true);
    else setIsLoading(true);

    setError(null);
    try {
      const [
        sprint,
        kpis,
        tickets,
        blockers,
        repositoryMismatches,
        integrations,
        teamReport,
        clientProgress,
        developerReport
      ] = await Promise.all([
        resolve(kpiApi.sprint.current(projectId)),
        resolve(kpiApi.sprint.kpis(projectId)),
        resolve(kpiApi.tickets.list(projectId)),
        resolve(kpiApi.blockers.list(projectId)),
        isDeveloper(user) ? Promise.resolve(null) : resolve(kpiApi.repository.mismatches(projectId)),
        isDeveloper(user) ? Promise.resolve([]) : resolve(kpiApi.integrations.list()),
        isExecutive(user) || isDeveloper(user) ? Promise.resolve(null) : resolve(kpiApi.developers.teamKpis(projectId)),
        isDeveloper(user) ? Promise.resolve(null) : resolve(kpiApi.developers.clientProgress(projectId)),
        isDeveloper(user) ? resolve(kpiApi.developers.developerMe(projectId)) : Promise.resolve(null)
      ]);

      setData({
        sprint,
        kpis,
        tickets: tickets ?? [],
        blockers: blockers ?? [],
        repositoryMismatches: repositoryMismatches ?? [],
        integrations: integrations ?? [],
        teamReport,
        clientProgress,
        developerReport
      });
    } catch (err) {
      setData(emptyBundle);
      setError(getErrorMessage(err));
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [projectId, user]);

  useEffect(() => {
    load();
  }, [load, refreshSignal]);

  return {
    data,
    isLoading,
    isRefreshing,
    error,
    refresh: () => load("refresh")
  };
}

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { Project } from "../domain/types";
import { kpiApi } from "../services/api";
import { appStorage, PROJECT_STORAGE_KEY } from "../services/storage";
import { useAuth } from "./AuthContext";
import { selectInitialProject } from "./projectSelection";

interface ProjectContextValue {
  projects: Project[];
  currentProject: Project | null;
  isLoadingProjects: boolean;
  error: string | null;
  selectProject: (project: Project) => Promise<void>;
  refreshProjects: () => Promise<void>;
}

const ProjectContext = createContext<ProjectContextValue | undefined>(undefined);

export function ProjectProvider({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [projects, setProjects] = useState<Project[]>([]);
  const [currentProject, setCurrentProject] = useState<Project | null>(null);
  const [isLoadingProjects, setIsLoadingProjects] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectProject = useCallback(async (project: Project) => {
    setCurrentProject(project);
    await appStorage.setItem(PROJECT_STORAGE_KEY, String(project.id));
  }, []);

  const refreshProjects = useCallback(async () => {
    if (!isAuthenticated) {
      setProjects([]);
      setCurrentProject(null);
      return;
    }

    setIsLoadingProjects(true);
    setError(null);
    try {
      const storedRaw = await appStorage.getItem(PROJECT_STORAGE_KEY);
      const storedId = storedRaw ? Number(storedRaw) : null;
      const list = await kpiApi.projects.list();
      const selected = selectInitialProject(list, Number.isFinite(storedId) ? storedId : null);
      setProjects(list);
      setCurrentProject(selected);
      if (selected) await appStorage.setItem(PROJECT_STORAGE_KEY, String(selected.id));
    } catch (err) {
      setProjects([]);
      setCurrentProject(null);
      setError(err instanceof Error ? err.message : "Could not load projects.");
    } finally {
      setIsLoadingProjects(false);
    }
  }, [isAuthenticated]);

  useEffect(() => {
    refreshProjects();
  }, [refreshProjects]);

  const value = useMemo<ProjectContextValue>(
    () => ({
      projects,
      currentProject,
      isLoadingProjects,
      error,
      selectProject,
      refreshProjects
    }),
    [currentProject, error, isLoadingProjects, projects, refreshProjects, selectProject]
  );

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProject() {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error("useProject must be used within ProjectProvider");
  return ctx;
}

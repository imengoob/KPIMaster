import { createContext, useCallback, useContext, useState, useEffect, ReactNode } from "react";
import { DateRange } from "react-day-picker";
import { projectApi } from "@/services/api/projects";
import type { BackendProject } from "@/services/api/types";
import type { PlatformFilter } from "@/lib/platforms";

export interface Project {
  id: number;
  name: string;
  key: string;
  color: string;
  repositoryUrl: string | null;
}

const PROJECT_COLORS = [
  "hsl(190, 95%, 45%)",
  "hsl(270, 70%, 55%)",
  "hsl(35, 90%, 55%)",
  "hsl(140, 60%, 45%)",
  "hsl(0, 72%, 55%)",
];

const STORAGE_KEY = "sprintpulse.currentProjectId";
const PLATFORM_STORAGE_KEY = "sprintpulse.platformFilter";

function toProject(p: BackendProject, idx: number): Project {
  return {
    id: p.id,
    name: p.name,
    key: p.key,
    color: PROJECT_COLORS[idx % PROJECT_COLORS.length],
    repositoryUrl: p.repository_url,
  };
}

interface ProjectContextType {
  currentProject: Project | null;
  setCurrentProject: (p: Project) => void;
  allProjects: Project[];
  isLoadingProjects: boolean;
  refreshProjects: (selectProjectId?: number) => Promise<Project[]>;
  globalDateRange: DateRange | undefined;
  setGlobalDateRange: (range: DateRange | undefined) => void;
  globalPlatformFilter: PlatformFilter;
  setGlobalPlatformFilter: (platform: PlatformFilter) => void;
}

const ProjectContext = createContext<ProjectContextType | undefined>(undefined);

function getRequestedProject(projects: Project[]): Project | undefined {
  /* v8 ignore next -- defensive SSR guard; ProjectProvider is exercised in browser/jsdom. */
  if (typeof window === "undefined") return undefined;

  const token = new URLSearchParams(window.location.search).get("project");
  if (!token) return undefined;

  const normalized = token.trim().toUpperCase();
  return projects.find(
    (project) => project.key.toUpperCase() === normalized || String(project.id) === token,
  );
}

function getStoredProjectId(): number | null {
  /* v8 ignore next -- defensive SSR guard; ProjectProvider is exercised in browser/jsdom. */
  if (typeof window === "undefined") return null;

  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;

  const parsed = Number(raw);
  return Number.isInteger(parsed) ? parsed : null;
}

function getStoredPlatformFilter(): PlatformFilter {
  /* v8 ignore next -- defensive SSR guard; ProjectProvider is exercised in browser/jsdom. */
  if (typeof window === "undefined") return "all";

  const raw = window.localStorage.getItem(PLATFORM_STORAGE_KEY);
  if (raw === "trello" || raw === "github" || raw === "jira" || raw === "microsoft" || raw === "all") {
    return raw;
  }
  return "all";
}

export const ProjectProvider = ({ children }: { children: ReactNode }) => {
  const [allProjects, setAllProjects] = useState<Project[]>([]);
  const [currentProject, setCurrentProjectState] = useState<Project | null>(null);
  const [isLoadingProjects, setIsLoadingProjects] = useState(true);
  const [globalDateRange, setGlobalDateRange] = useState<DateRange | undefined>(undefined);
  const [globalPlatformFilter, setGlobalPlatformFilterState] = useState<PlatformFilter>(() => getStoredPlatformFilter());

  const setCurrentProject = useCallback((project: Project) => {
    setCurrentProjectState(project);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, String(project.id));
    }
  }, []);

  const setGlobalPlatformFilter = useCallback((platform: PlatformFilter) => {
    setGlobalPlatformFilterState(platform);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(PLATFORM_STORAGE_KEY, platform);
    }
  }, []);

  const refreshProjects = useCallback(async (selectProjectId?: number): Promise<Project[]> => {
    setIsLoadingProjects(true);
    try {
      const list = await projectApi.getAll();
      const mapped = list.map(toProject);
      setAllProjects(mapped);
      if (mapped.length === 0) {
        setCurrentProjectState(null);
        return mapped;
      }
      const requested = getRequestedProject(mapped);
      const selected = selectProjectId == null
        ? undefined
        : mapped.find((project) => project.id === selectProjectId);
      const storedId = getStoredProjectId();
      const stored = storedId == null ? undefined : mapped.find((project) => project.id === storedId);
      const initialProject = selected ?? requested ?? stored ?? mapped[0];
      setCurrentProject(initialProject);
      return mapped;
    } catch {
      setAllProjects([]);
      setCurrentProjectState(null);
      return [];
    } finally {
      setIsLoadingProjects(false);
    }
  }, [setCurrentProject]);

  useEffect(() => {
    let cancelled = false;
    refreshProjects().finally(() => {
      if (cancelled) return;
    });
    return () => {
      cancelled = true;
    };
  }, [refreshProjects]);

  return (
    <ProjectContext.Provider
      value={{
        currentProject,
        setCurrentProject,
        allProjects,
        isLoadingProjects,
        refreshProjects,
        globalDateRange,
        setGlobalDateRange,
        globalPlatformFilter,
        setGlobalPlatformFilter,
      }}
    >
      {children}
    </ProjectContext.Provider>
  );
};

export const useProject = () => {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error("useProject must be used within a ProjectProvider");
  return ctx;
};

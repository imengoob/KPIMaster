import type { Project } from "../domain/types";

export function selectInitialProject(projects: Project[], storedProjectId: number | null): Project | null {
  if (!projects.length) return null;
  if (storedProjectId !== null) {
    const stored = projects.find((project) => project.id === storedProjectId);
    if (stored) return stored;
  }
  return projects[0] ?? null;
}

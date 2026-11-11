import { selectInitialProject } from "../state/projectSelection";
import type { Project } from "../domain/types";

const projects: Project[] = [
  {
    id: 1,
    name: "Horizon",
    key: "HZ",
    description: null,
    repository_url: null,
    slack_channel: null,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z"
  },
  {
    id: 2,
    name: "Retail",
    key: "RT",
    description: null,
    repository_url: null,
    slack_channel: null,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z"
  }
];

describe("project selection", () => {
  it("restores the stored project when it is visible", () => {
    expect(selectInitialProject(projects, 2)?.key).toBe("RT");
  });

  it("falls back to the first visible project when stored scope is unavailable", () => {
    expect(selectInitialProject(projects, 99)?.key).toBe("HZ");
  });

  it("returns null for empty project scopes", () => {
    expect(selectInitialProject([], 1)).toBeNull();
  });
});

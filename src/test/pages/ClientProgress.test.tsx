import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { useQuery } from "@tanstack/react-query";

vi.mock("@tanstack/react-query", () => ({
  useQuery: vi.fn(),
}));

vi.mock("@/components/DashboardLayout", () => ({
  default: ({ children }: { children: React.ReactNode }) => <div data-testid="layout">{children}</div>,
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({
    currentProject: { id: 7, name: "Norma Client Delivery", key: "NCD", color: "#000", repositoryUrl: null },
    setCurrentProject: vi.fn(),
    allProjects: [],
    isLoadingProjects: false,
    globalDateRange: undefined,
    globalPlatformFilter: "all",
    setGlobalPlatformFilter: vi.fn(),
  }),
}));

describe("ClientProgress", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
  });

  it("shows loading state", async () => {
    vi.mocked(useQuery).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as ReturnType<typeof useQuery>);

    const mod = await import("@/pages/ClientProgress");
    const ClientProgress = mod.default;

    render(<ClientProgress />);
    expect(screen.getByTestId("loading-spinner")).toBeInTheDocument();
  });

  it("shows error state", async () => {
    vi.mocked(useQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as ReturnType<typeof useQuery>);

    const mod = await import("@/pages/ClientProgress");
    const ClientProgress = mod.default;

    render(<ClientProgress />);
    expect(screen.getByTestId("error-state")).toBeInTheDocument();
  });

  it("renders client-facing delivery summary and member risks", async () => {
    vi.mocked(useQuery).mockReturnValue({
      data: {
        project_id: 7,
        sprint_id: null,
        summary: {
          total_developers: 2,
          on_track_count: 1,
          at_risk_count: 0,
          behind_count: 1,
          overall_completion_rate: 0.75,
          story_points_completed: 12,
          story_points_total: 16,
          active_blockers: 1,
          avg_cycle_time_hours: 10,
          last_updated_at: "2026-04-14T08:00:00Z",
        },
        members: [
          {
            developer_id: 1,
            developer_name: "Alice Chen",
            role: "member",
            status: "behind",
            tickets_completed: 2,
            tickets_total: 4,
            story_points_completed: 5,
            story_points_total: 8,
            active_work_items: 1,
            active_blockers: 1,
            avg_cycle_time_hours: 12,
            latest_activity_at: "2026-04-14T07:00:00Z",
            activity_freshness: "active",
            risk_note: "1 blocked work item is slowing delivery.",
          },
          {
            developer_id: 2,
            developer_name: "Bob Martin",
            role: "member",
            status: "on-track",
            tickets_completed: 3,
            tickets_total: 3,
            story_points_completed: 7,
            story_points_total: 8,
            active_work_items: 0,
            active_blockers: 0,
            avg_cycle_time_hours: 8,
            latest_activity_at: "2026-04-13T09:00:00Z",
            activity_freshness: "recent",
            risk_note: null,
          },
        ],
        computed_at: "2026-04-14T08:00:00Z",
      },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useQuery>);

    const mod = await import("@/pages/ClientProgress");
    const ClientProgress = mod.default;

    render(<ClientProgress />);

    expect(screen.getByText(/Client Progress for Norma Client Delivery/i)).toBeInTheDocument();
    expect(screen.getByText(/1 on track, 0 at risk, 1 behind/i)).toBeInTheDocument();
    expect(screen.getByText("Alice Chen")).toBeInTheDocument();
    expect(screen.getByText(/slowing delivery/i)).toBeInTheDocument();
    expect(screen.getByText(/Delivery is moving as expected/i)).toBeInTheDocument();
  });
});

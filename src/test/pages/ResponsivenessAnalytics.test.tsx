import React from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ResponsivenessAnalytics from "@/pages/ResponsivenessAnalytics";

vi.mock("@/components/DashboardLayout", () => ({
  default: ({ children }: { children: React.ReactNode }) => <div data-testid="layout">{children}</div>,
}));

const projectState = vi.hoisted(() => ({
  currentProject: { id: 1, name: "Phoenix", key: "PHX", color: "#000", repositoryUrl: null } as any,
  globalDateRange: undefined,
  globalPlatformFilter: "all" as "all" | "github",
}));

const responsivenessState = vi.hoisted(() => ({
  data: null as any,
  isLoading: false,
  isError: false,
  error: null as Error | null,
  refetch: vi.fn(),
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => projectState,
}));

vi.mock("@/hooks/useResponsiveness", () => ({
  useResponsivenessAnalytics: () => responsivenessState,
}));

describe("ResponsivenessAnalytics", () => {
  beforeEach(() => {
    projectState.currentProject = { id: 1, name: "Phoenix", key: "PHX", color: "#000", repositoryUrl: null };
    projectState.globalPlatformFilter = "all";
    responsivenessState.data = {
      global_avg_reaction_hours: 2,
      global_avg_response_hours: 3,
      active_developers: 1,
      dormant_developers: 0,
      total_sla_breaches: 1,
      developers: [
        {
          developer_id: 5,
          developer_name: "Alice Chen",
          total_reactions: 4,
          total_comments: 2,
          avg_first_reaction_hours: 2,
          avg_first_response_hours: 3,
          inactivity_duration_hours: null,
          sla_breaching_tickets: 1,
        },
      ],
      trend: [],
    };
    responsivenessState.isLoading = false;
    responsivenessState.isError = false;
    responsivenessState.error = null;
  });

  it("shows a no-workspace error when no project is selected", () => {
    projectState.currentProject = null;
    render(<ResponsivenessAnalytics />);
    expect(screen.getByText(/No Workspace Selected/i)).toBeInTheDocument();
  });

  it("shows a platform guard for non-trello providers", () => {
    projectState.globalPlatformFilter = "github";
    render(<ResponsivenessAnalytics />);
    expect(screen.getByText(/Switch the platform filter from GitHub to Trello or All Platforms/i)).toBeInTheDocument();
  });

  it("shows a loading spinner while metrics are loading", () => {
    responsivenessState.isLoading = true;
    render(<ResponsivenessAnalytics />);
    expect(screen.getByTestId("loading-spinner")).toBeInTheDocument();
  });

  it("shows an error state when the query fails", () => {
    responsivenessState.isError = true;
    responsivenessState.error = new Error("Boom");
    render(<ResponsivenessAnalytics />);
    expect(screen.getByText(/Boom/i)).toBeInTheDocument();
  });

  it("renders responsiveness metrics and developer rows", () => {
    render(<ResponsivenessAnalytics />);
    expect(screen.getByText("Responsiveness Analytics")).toBeInTheDocument();
    expect(screen.getByText("Alice Chen")).toBeInTheDocument();
    expect(screen.getByText(/1 Breach/i)).toBeInTheDocument();
  });
});

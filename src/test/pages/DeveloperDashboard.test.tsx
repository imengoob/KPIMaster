import React from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DeveloperDashboard from "@/pages/DeveloperDashboard";

vi.mock("@/components/DashboardLayout", () => ({
  default: ({ children }: { children: React.ReactNode }) => <div data-testid="layout">{children}</div>,
}));

const projectState = vi.hoisted(() => ({
  currentProject: { id: 2, name: "Phoenix", key: "PHX", color: "#000", repositoryUrl: null } as any,
  globalDateRange: undefined,
  globalPlatformFilter: "github",
}));

const authState = vi.hoisted(() => ({
  user: {
    id: 1,
    username: "alice",
    email: "alice@example.com",
    role: "developer",
    company_id: null,
    developer_id: 5,
    kpi_subject_id: 5,
    is_active: true,
  } as any,
  isDeveloper: true,
}));

const useQueryMock = vi.hoisted(() => vi.fn());

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => projectState,
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: authState.user }),
  isDeveloperUser: () => authState.isDeveloper,
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: any[]) => useQueryMock(...args),
}));

describe("DeveloperDashboard", () => {
  beforeEach(() => {
    projectState.currentProject = { id: 2, name: "Phoenix", key: "PHX", color: "#000", repositoryUrl: null };
    projectState.globalPlatformFilter = "github";
    authState.isDeveloper = true;
    authState.user = {
      id: 1,
      username: "alice",
      email: "alice@example.com",
      role: "developer",
      company_id: null,
      developer_id: 5,
      kpi_subject_id: 5,
      is_active: true,
    };
    useQueryMock.mockReset();
  });

  it("blocks non-developer users", () => {
    authState.isDeveloper = false;
    render(<DeveloperDashboard />);
    expect(screen.getByText(/Only Developers can access the Personal Dashboard/i)).toBeInTheDocument();
  });

  it("shows an empty state when no project is selected", () => {
    projectState.currentProject = null;
    useQueryMock.mockReturnValue({ data: null, isLoading: false, isError: false });
    render(<DeveloperDashboard />);
    expect(screen.getByText(/Link a Project to view your personal KPIs/i)).toBeInTheDocument();
  });

  it("shows a loading state while KPIs are loading", () => {
    useQueryMock.mockImplementation(() => ({ data: null, isLoading: true, isError: false }));
    render(<DeveloperDashboard />);
    expect(screen.getByTestId("loading-spinner")).toBeInTheDocument();
  });

  it("shows the no-records state when KPI lookup fails", () => {
    useQueryMock.mockImplementation(() => ({ data: null, isLoading: false, isError: true }));
    render(<DeveloperDashboard />);
    expect(screen.getByText(/No KPI Records Found/i)).toBeInTheDocument();
  });

  it("renders KPI content and includes the platform in the query key", () => {
    const seenKeys: unknown[] = [];
    useQueryMock.mockImplementation(({ queryKey }: { queryKey: unknown[] }) => {
      seenKeys.push(queryKey);
      if ((queryKey[0] as string) === "dev-kpis-me") {
        return {
          data: {
            developer_id: 5,
            developer_name: "Alice Chen",
            developer_role: "Software Engineer",
            tickets_done: 6,
            tickets_total: 8,
            active_blockers: 1,
            avg_cycle_time_hours: 12,
            comment_response_time_hours: 3,
            question_response_time_hours: 3,
            avg_blocker_age_hours: 8,
            unanswered_questions_count: 0,
            completion_rate: 0.75,
            blocker_count: 1,
            status: "on-track",
            ert_status: "within-target",
            computed_at: "2026-04-14T08:00:00Z",
          },
          isLoading: false,
          isError: false,
        };
      }
      if ((queryKey[0] as string) === "sprints") {
        return { data: [], isLoading: false, isError: false };
      }
      return {
        data: [{ avg_cycle_time_hours: 14, completion_rate: 0.5, blocker_count: 2, question_response_time_hours: 4 }],
        isLoading: false,
        isError: false,
      };
    });

    render(<DeveloperDashboard />);

    expect(screen.getByText(/Tracking Phoenix/i)).toBeInTheDocument();
    expect(screen.getByText("Alice Chen")).toBeInTheDocument();
    expect(screen.getByText(/6 \/ 8/i)).toBeInTheDocument();
    expect(seenKeys[0]).toEqual(["dev-kpis-me", 2, "all", undefined, undefined, "github"]);
  });
});

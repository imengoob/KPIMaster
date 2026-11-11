import React from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import VendorDashboard from "@/pages/VendorDashboard";

vi.mock("@/components/DashboardLayout", () => ({
  default: ({ children }: { children: React.ReactNode }) => <div data-testid="layout">{children}</div>,
}));

const projectState = vi.hoisted(() => ({
  currentProject: { id: 7, name: "Vendor Project", key: "VND", color: "#000", repositoryUrl: null } as any,
  globalDateRange: undefined,
  globalPlatformFilter: "github",
}));

const queryState = vi.hoisted(() => ({
  data: null as any,
  isPending: false,
  isError: false,
  error: null as Error | null,
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => projectState,
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: () => queryState,
}));

describe("VendorDashboard", () => {
  beforeEach(() => {
    projectState.currentProject = { id: 7, name: "Vendor Project", key: "VND", color: "#000", repositoryUrl: null };
    queryState.isPending = false;
    queryState.isError = false;
    queryState.error = null;
    queryState.data = {
      summary: {
        total_developers: 1,
        on_track_count: 1,
        at_risk_count: 0,
        behind_count: 0,
        overall_completion_rate: 0.75,
        story_points_completed: 6,
        story_points_total: 8,
        active_blockers: 0,
        avg_cycle_time_hours: 10,
        last_updated_at: "2026-04-14T08:00:00Z",
      },
      members: [
        {
          developer_id: 1,
          developer_name: "Alice Chen",
          role: "developer",
          status: "on-track",
          tickets_completed: 3,
          tickets_total: 4,
          story_points_completed: 6,
          story_points_total: 8,
          active_work_items: 1,
          active_blockers: 0,
          avg_cycle_time_hours: 10,
          latest_activity_at: "2026-04-14T07:00:00Z",
          activity_freshness: "active",
          risk_note: null,
        },
      ],
      computed_at: "2026-04-14T08:00:00Z",
    };
  });

  it("shows an empty project state when no project is selected", () => {
    projectState.currentProject = null;
    render(<VendorDashboard />);
    expect(screen.getByText(/Link a Project to monitor outsourcing KPIs/i)).toBeInTheDocument();
  });

  it("shows a loading spinner while the report is pending", () => {
    queryState.isPending = true;
    render(<VendorDashboard />);
    expect(screen.getByTestId("loading-spinner")).toBeInTheDocument();
  });

  it("shows an error state when the query fails", () => {
    queryState.isError = true;
    queryState.error = new Error("Vendor API failed");
    render(<VendorDashboard />);
    expect(screen.getByText(/Vendor API failed/i)).toBeInTheDocument();
  });

  it("shows the empty vendor message when there are no members", () => {
    queryState.data = { members: [], summary: { total_developers: 0 } };
    render(<VendorDashboard />);
    expect(screen.getByText(/No Subcontractors Found/i)).toBeInTheDocument();
  });

  it("renders the vendor KPI summary and member cards", () => {
    render(<VendorDashboard />);
    expect(screen.getByText(/Outsourcing Subcontractor KPIs/i)).toBeInTheDocument();
    expect(screen.getByText(/Vendor Progress for Vendor Project/i)).toBeInTheDocument();
    expect(screen.getByText("Alice Chen")).toBeInTheDocument();
    expect(screen.getByText(/1 on track, 0 at risk, 0 behind/i)).toBeInTheDocument();
  });
});

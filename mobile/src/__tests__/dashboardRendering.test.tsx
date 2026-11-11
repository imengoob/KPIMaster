import React from "react";
import { render, screen } from "@testing-library/react-native";
import { MetricCard } from "../components/MetricCard";
import { summarizeDashboard } from "../services/adapters";
import type { DashboardBundle } from "../domain/types";

const bundle: DashboardBundle = {
  sprint: {
    id: 1,
    project_id: 1,
    name: "Sprint 8",
    goal: "Ship mobile audit",
    start_date: "2026-05-01",
    end_date: "2026-05-14",
    status: "active",
    committed_points: 40,
    completed_points: 20,
    velocity: 18
  },
  kpis: {
    project_id: 1,
    sprint_id: 1,
    current_kpis: {
      id: 1,
      project_id: 1,
      sprint_id: 1,
      cycle_time_hours: 12,
      lead_time_hours: 18,
      velocity: 18,
      completion_rate: 0.5,
      estimation_accuracy: 0.8,
      throughput: 3,
      bug_rate: 0.1,
      computed_at: "2026-05-01T00:00:00Z"
    },
    velocity_trend: [12, 18],
    completion_trend: [0.3, 0.5],
    open_blockers: 1,
    stalled_tickets: 1,
    repo_mismatches: 2
  },
  tickets: [],
  blockers: [],
  repositoryMismatches: [],
  integrations: [],
  teamReport: null,
  clientProgress: null,
  developerReport: null
};

describe("dashboard rendering helpers", () => {
  it("summarizes project-scoped KPI data", () => {
    const summary = summarizeDashboard(bundle);
    expect(summary.sprintName).toBe("Sprint 8");
    expect(summary.completionRate).toBe("50%");
    expect(summary.repoMismatches).toBe(2);
  });

  it("renders a readable metric card", () => {
    render(<MetricCard label="Completion" value="50%" helper="20/40 points" tone="success" />);
    expect(screen.getByText("Completion")).toBeTruthy();
    expect(screen.getByText("50%")).toBeTruthy();
    expect(screen.getByText("20/40 points")).toBeTruthy();
  });
});

/**
 * Dashboard page smoke tests.
 * Hooks are module-mocked; no real HTTP calls.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import Dashboard from "@/pages/Dashboard";

// ── Stub DashboardLayout to avoid Router/AppSidebar dependency ────────────────
vi.mock("@/components/DashboardLayout", () => ({
  default: ({ children }: { children: React.ReactNode }) => <div data-testid="layout">{children}</div>,
}));

// ── Mock contexts ─────────────────────────────────────────────────────────────

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({
    currentProject: { id: 1, name: "KPIMaster Platform", key: "PHX", color: "#000", repositoryUrl: null },
    setCurrentProject: vi.fn(),
    allProjects: [],
    isLoadingProjects: false,
    globalDateRange: undefined,
    globalPlatformFilter: "all",
    setGlobalPlatformFilter: vi.fn(),
  }),
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: () => ({ data: null, isLoading: false, isError: false }),
}));

// ── Mock hooks ────────────────────────────────────────────────────────────────

const SPRINT_DATA = {
  id: 10,
  name: "PHX-S2: Acceleration",
  startDate: "2026-04-03",
  endDate: "2026-04-17",
  daysRemaining: 7,
  totalTickets: 10,
  completedTickets: 5,
  inProgressTickets: 3,
  notStartedTickets: 1,
  blockedTickets: 1,
  committedPoints: 40,
  completedPoints: 20,
  velocity: 20,
  previousVelocity: 18,
};

const KPI_DATA = {
  velocity:           { value: "38", change: "+9%", type: "positive" as const },
  cycleTime:          { value: "3.0d", change: "-10%", type: "neutral" as const },
  leadTime:           { value: "6.0d", change: "N/A", type: "neutral" as const },
  estimationAccuracy: { value: "82%", change: "N/A", type: "positive" as const },
  blockedCount:       { value: 2, change: "1 stalled", type: "negative" as const },
  completionRate:     { value: "84%", change: "N/A", type: "positive" as const },
};

vi.mock("@/hooks/useSprintData", () => ({
  useCurrentSprint:   vi.fn(),
  useSprintKpis:      vi.fn(),
  useBurndown:        vi.fn(),
  useVelocityHistory: vi.fn(),
  useBlockers:        vi.fn(),
}));

// ── Helpers ───────────────────────────────────────────────────────────────────

import * as hooks from "@/hooks/useSprintData";

function setupHooks({
  sprintLoading = false,
  sprintError = false,
  kpiLoading = false,
  kpiError = false,
} = {}) {
  vi.mocked(hooks.useCurrentSprint).mockReturnValue({
    data: sprintLoading || sprintError ? undefined : SPRINT_DATA,
    isLoading: sprintLoading,
    isError: sprintError,
    error: null,
  });
  vi.mocked(hooks.useSprintKpis).mockReturnValue({
    data: kpiLoading || kpiError ? undefined : KPI_DATA,
    isLoading: kpiLoading,
    isError: kpiError,
  } as ReturnType<typeof hooks.useSprintKpis>);
  vi.mocked(hooks.useBurndown).mockReturnValue({
    data: [{ day: "2026-04-03", ideal: 40, actual: 40 }],
    isLoading: false, isError: false,
  } as ReturnType<typeof hooks.useBurndown>);
  vi.mocked(hooks.useVelocityHistory).mockReturnValue({
    data: [{ sprint: "S1", points: 30 }, { sprint: "S2", points: 38 }],
    isLoading: false, isError: false,
  } as ReturnType<typeof hooks.useVelocityHistory>);
  vi.mocked(hooks.useBlockers).mockReturnValue({
    data: [],
    isLoading: false, isError: false,
  } as ReturnType<typeof hooks.useBlockers>);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("Dashboard", () => {
  beforeEach(() => {
    setupHooks();
  });

  it("renders sprint name and project name", () => {
    render(<Dashboard />);
    expect(screen.getByText(/PHX-S2: Acceleration/)).toBeInTheDocument();
    expect(screen.getByText(/KPIMaster Platform/)).toBeInTheDocument();
  });

  it("shows LoadingSpinner while sprint or kpi is loading", () => {
    setupHooks({ sprintLoading: true });
    render(<Dashboard />);
    expect(screen.getByTestId("loading-spinner")).toBeInTheDocument();
  });

  it("shows ErrorState when sprint query fails", () => {
    setupHooks({ sprintError: true });
    render(<Dashboard />);
    expect(screen.getByTestId("error-state")).toBeInTheDocument();
  });

  it("shows ErrorState when kpi query fails", () => {
    setupHooks({ kpiError: true });
    render(<Dashboard />);
    expect(screen.getByTestId("error-state")).toBeInTheDocument();
  });

  it("renders sprint date range and days remaining", () => {
    render(<Dashboard />);
    expect(screen.getByText(/2026-04-03/)).toBeInTheDocument();
    expect(screen.getByText(/7 days remaining/)).toBeInTheDocument();
  });

  it("renders KPI section headings", () => {
    render(<Dashboard />);
    expect(screen.getByText("Velocity")).toBeInTheDocument();
    expect(screen.getByText("Cycle Time")).toBeInTheDocument();
    expect(screen.getByText("Completion")).toBeInTheDocument();
  });

  it("renders Sprint Burndown chart section", () => {
    render(<Dashboard />);
    expect(screen.getByText("Sprint Burndown")).toBeInTheDocument();
  });

  it("renders Velocity Trend section", () => {
    render(<Dashboard />);
    expect(screen.getByText("Velocity Trend")).toBeInTheDocument();
  });

  it("renders Sprint Progress section with ticket count", () => {
    render(<Dashboard />);
    expect(screen.getByText("Sprint Progress")).toBeInTheDocument();
    expect(screen.getByText(/5\/10 tickets completed/)).toBeInTheDocument();
  });

  it("shows 'No active blockers' when blockers list is empty", () => {
    render(<Dashboard />);
    expect(screen.getByText(/No active blockers/)).toBeInTheDocument();
  });

  it("shows 'Sprint ends today' when daysRemaining is 0", () => {
    vi.mocked(hooks.useCurrentSprint).mockReturnValue({
      data: { ...SPRINT_DATA, daysRemaining: 0 },
      isLoading: false,
      isError: false,
      error: null,
    });
    render(<Dashboard />);
    expect(screen.getByText(/Sprint ends today/)).toBeInTheDocument();
  });
});

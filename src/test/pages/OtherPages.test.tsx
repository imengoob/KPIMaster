/**
 * Smoke tests for the remaining 5 pages.
 * Each test verifies: loading state, error state, and basic content render.
 * DashboardLayout is mocked to avoid Router dependency.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

const queryMock = vi.hoisted(() => ({
  state: {
    data: null as unknown,
    isLoading: false,
    isError: false,
  },
}));

// ── Stub DashboardLayout ──────────────────────────────────────────────────────
vi.mock("@/components/DashboardLayout", () => ({
  default: ({ children }: { children: React.ReactNode }) => <div data-testid="layout">{children}</div>,
}));

// ── Stub ProjectContext ───────────────────────────────────────────────────────
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

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: 1,
      username: "admin",
      email: "admin@example.com",
      role: "company_admin",
      kpi_subject_id: null,
    },
  }),
  isDeveloperUser: () => false,
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: () => queryMock.state,
  useQueryClient: () => ({
    invalidateQueries: vi.fn(),
  }),
  useMutation: () => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
  }),
}));

// ── Mock all hooks ────────────────────────────────────────────────────────────
vi.mock("@/hooks/useSprintData", () => ({
  useCurrentSprint:        vi.fn(),
  useSprintKpis:           vi.fn(),
  useBurndown:             vi.fn(),
  useVelocityHistory:      vi.fn(),
  useBlockers:             vi.fn(),
  useTickets:              vi.fn(),
  useDevelopers:           vi.fn(),
  useRepositoryMismatches: vi.fn(),
}));

import * as hooks from "@/hooks/useSprintData";

// ── Fixture data ──────────────────────────────────────────────────────────────

const SPRINT = {
  id: 10, name: "PHX-S2", startDate: "2026-04-03", endDate: "2026-04-17",
  daysRemaining: 7, totalTickets: 5, completedTickets: 2, inProgressTickets: 2,
  notStartedTickets: 1, blockedTickets: 0, committedPoints: 40, completedPoints: 20,
  velocity: 20, previousVelocity: 18,
};

const KPI = {
  velocity:           { value: "38", change: "+9%",  type: "positive" as const },
  cycleTime:          { value: "3d", change: "N/A",  type: "neutral"  as const },
  leadTime:           { value: "6d", change: "N/A",  type: "neutral"  as const },
  estimationAccuracy: { value: "82%", change: "N/A", type: "positive" as const },
  blockedCount:       { value: 1, change: "0 stalled", type: "negative" as const },
  completionRate:     { value: "84%", change: "N/A", type: "positive" as const },
};

const TICKETS = [
  { id: "T-1", numericId: 1, title: "Auth bug", assigneeId: 5, status: "in-progress" as const,
    priority: "high" as const, storyPoints: 3, dueDate: "2026-04-10", qualityScore: 80,
    labels: ["bug"], stalledHours: undefined },
  { id: "T-2", numericId: 2, title: "Add feature", assigneeId: 6, status: "completed" as const,
    priority: "medium" as const, storyPoints: 2, dueDate: "2026-04-09", qualityScore: 90,
    labels: ["story"], stalledHours: undefined },
];

const BLOCKERS = [
  { id: 7, ticketId: "T-2", title: "Auth bug", assigneeId: 5,
    stalledHours: 30, escalationLevel: 2 as const,
    reason: "No commits", impact: "Team delivery at risk", lastActivity: "5h ago" },
];

const DEVELOPERS = [
  { id: 5, name: "Alice Chen", avatar: "AC", role: "developer",
    completedPoints: 10, totalPoints: 20, ticketsCompleted: 2, ticketsTotal: 4,
    avgCycleTime: 8, estimationAccuracy: 85, status: "on-track" as const, blockers: 0 },
];

const REPO_MISMATCHES = [
  { ticket: "T-1", ticketId: 1, branch: "feature/1", commits: 0, prs: 0,
    prStatus: "none" as const, lastCommit: "Never", mismatch: true,
    mismatchReason: "No commits", mismatchType: "no_commits_in_progress" },
];

const TEAM_KPIS = {
  project_id: 1,
  sprint_id: null,
  members: [
    {
      developer_id: 5,
      developer_name: "Alice Chen",
      role: "developer",
      provider_sources: ["github"],
      story_points_completed: 10,
      story_points_total: 20,
      completion_rate: 0.5,
      avg_cycle_time_hours: 8,
      blocker_rate: 0,
      active_blockers: 0,
      question_response_time_hours: 2,
      unanswered_question_rate: 0,
      ert_target_hours: 4,
      ert_status: "within-target",
      status: "on-track",
      warning_count: 0,
    },
  ],
  team_completion_rate: 0.5,
  team_avg_cycle_time_hours: 8,
  team_blocker_rate: 0,
  team_question_response_time_hours: 2,
  team_unanswered_question_rate: 0,
  warning_signals: [],
  computed_at: "2026-04-29T00:00:00Z",
};

// ── Setup helper ──────────────────────────────────────────────────────────────

function setupAllHooks({
  loading = false,
  error   = false,
} = {}) {
  queryMock.state = {
    data: loading || error ? null : TEAM_KPIS,
    isLoading: loading,
    isError: error,
  };
  const base = { isLoading: loading, isError: error };
  vi.mocked(hooks.useCurrentSprint).mockReturnValue({ data: loading || error ? undefined : SPRINT, ...base, error: null });
  vi.mocked(hooks.useSprintKpis).mockReturnValue({ data: loading || error ? undefined : KPI, ...base } as ReturnType<typeof hooks.useSprintKpis>);
  vi.mocked(hooks.useBurndown).mockReturnValue({ data: [], ...base } as ReturnType<typeof hooks.useBurndown>);
  vi.mocked(hooks.useTickets).mockReturnValue({ data: loading || error ? undefined : TICKETS, ...base } as ReturnType<typeof hooks.useTickets>);
  vi.mocked(hooks.useBlockers).mockReturnValue({ data: loading || error ? undefined : BLOCKERS, ...base } as ReturnType<typeof hooks.useBlockers>);
  vi.mocked(hooks.useDevelopers).mockReturnValue({ data: loading || error ? undefined : DEVELOPERS, ...base } as ReturnType<typeof hooks.useDevelopers>);
  vi.mocked(hooks.useRepositoryMismatches).mockReturnValue({ data: loading || error ? undefined : REPO_MISMATCHES, ...base } as ReturnType<typeof hooks.useRepositoryMismatches>);
}

// ── BlockerDetection ──────────────────────────────────────────────────────────

describe("BlockerDetection", () => {
  let BlockerDetection: React.ComponentType;

  beforeEach(async () => {
    setupAllHooks();
    const mod = await import("@/pages/BlockerDetection");
    BlockerDetection = mod.default;
  });

  it("shows loading spinner", () => {
    setupAllHooks({ loading: true });
    render(<BlockerDetection />);
    expect(screen.getByTestId("loading-spinner")).toBeInTheDocument();
  });

  it("shows error state", () => {
    setupAllHooks({ error: true });
    render(<BlockerDetection />);
    expect(screen.getByTestId("error-state")).toBeInTheDocument();
  });

  it("renders escalation filters", () => {
    render(<BlockerDetection />);
    expect(screen.getByRole("button", { name: /all \(1\)/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^level 2 \(1\)$/i })).toBeInTheDocument();
  });

  it("renders blocker card with title", () => {
    render(<BlockerDetection />);
    expect(screen.getByText("Auth bug")).toBeInTheDocument();
  });
});

// ── TicketAnalysis ────────────────────────────────────────────────────────────

describe("TicketAnalysis", () => {
  let TicketAnalysis: React.ComponentType;

  beforeEach(async () => {
    setupAllHooks();
    const mod = await import("@/pages/TicketAnalysis");
    TicketAnalysis = mod.default;
  });

  it("shows loading spinner", () => {
    setupAllHooks({ loading: true });
    render(<TicketAnalysis />);
    expect(screen.getByTestId("loading-spinner")).toBeInTheDocument();
  });

  it("shows error state", () => {
    setupAllHooks({ error: true });
    render(<TicketAnalysis />);
    expect(screen.getByTestId("error-state")).toBeInTheDocument();
  });

  it("renders page heading", () => {
    render(<TicketAnalysis />);
    expect(screen.getByText(/Average Quality/i)).toBeInTheDocument();
  });

  it("renders ticket rows", () => {
    render(<TicketAnalysis />);
    expect(screen.getByText("Auth bug")).toBeInTheDocument();
    expect(screen.getByText("Add feature")).toBeInTheDocument();
  });
});

// ── DeveloperProgress ─────────────────────────────────────────────────────────

describe("DeveloperProgress", () => {
  let DeveloperProgress: React.ComponentType;

  beforeEach(async () => {
    setupAllHooks();
    const mod = await import("@/pages/DeveloperProgress");
    DeveloperProgress = mod.default;
  });

  it("shows loading spinner", () => {
    setupAllHooks({ loading: true });
    render(<DeveloperProgress />);
    expect(screen.getByTestId("loading-spinner")).toBeInTheDocument();
  });

  it("shows error state", () => {
    setupAllHooks({ error: true });
    render(<DeveloperProgress />);
    expect(screen.getByTestId("error-state")).toBeInTheDocument();
  });

  it("renders page heading with project name", () => {
    render(<DeveloperProgress />);
    expect(screen.getByText(/Developer KPI Dashboard/i)).toBeInTheDocument();
    expect(screen.getByText(/1 developer/i)).toBeInTheDocument();
  });

  it("renders developer name", () => {
    render(<DeveloperProgress />);
    expect(screen.getByText("Alice Chen")).toBeInTheDocument();
  });
});

// ── SprintMonitor ─────────────────────────────────────────────────────────────

describe("SprintMonitor", () => {
  let SprintMonitor: React.ComponentType;

  beforeEach(async () => {
    setupAllHooks();
    const mod = await import("@/pages/SprintMonitor");
    SprintMonitor = mod.default;
  });

  it("shows loading spinner", () => {
    setupAllHooks({ loading: true });
    render(<SprintMonitor />);
    expect(screen.getByTestId("loading-spinner")).toBeInTheDocument();
  });

  it("shows error state", () => {
    setupAllHooks({ error: true });
    render(<SprintMonitor />);
    expect(screen.getByTestId("error-state")).toBeInTheDocument();
  });

  it("renders sprint name in heading", () => {
    render(<SprintMonitor />);
    expect(screen.getByText(/PHX-S2/)).toBeInTheDocument();
  });

  it("renders ticket list section", () => {
    render(<SprintMonitor />);
    expect(screen.getByText("Auth bug")).toBeInTheDocument();
  });
});

// ── RepositoryIntegration ─────────────────────────────────────────────────────

describe("RepositoryIntegration", () => {
  let RepositoryIntegration: React.ComponentType;

  beforeEach(async () => {
    setupAllHooks();
    const mod = await import("@/pages/RepositoryIntegration");
    RepositoryIntegration = mod.default;
  });

  it("shows loading spinner", () => {
    setupAllHooks({ loading: true });
    render(<RepositoryIntegration />);
    expect(screen.getByTestId("loading-spinner")).toBeInTheDocument();
  });

  it("shows error state", () => {
    setupAllHooks({ error: true });
    render(<RepositoryIntegration />);
    expect(screen.getByTestId("error-state")).toBeInTheDocument();
  });

  it("renders page heading with project name", () => {
    render(<RepositoryIntegration />);
    expect(screen.getByText(/Repository/i)).toBeInTheDocument();
    expect(screen.getByText(/KPIMaster Platform/)).toBeInTheDocument();
  });

  it("renders mismatch entry", () => {
    render(<RepositoryIntegration />);
    // At least one "T-1" ticket ref should appear
    const refs = screen.getAllByText("T-1");
    expect(refs.length).toBeGreaterThan(0);
  });
});

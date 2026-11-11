/**
 * Hook integration tests for useSprintData.
 * Real QueryClient + mocked global fetch.
 * Each test creates a fresh QueryClient to avoid cache bleed.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import {
  useCurrentSprint,
  useSprintKpis,
  useBurndown,
  useVelocityHistory,
  useBlockers,
  useTickets,
} from "@/hooks/useSprintData";

// ── Fixtures ─────────────────────────────────────────────────────────────────

const SPRINT = {
  id: 10,
  project_id: 1,
  name: "PHX-S2",
  goal: "Ship it",
  start_date: "2026-04-03",
  end_date: "2026-04-17",
  status: "active",
  committed_points: 40,
  completed_points: 20,
  velocity: 20,
  created_at: "2026-04-03T00:00:00Z",
  updated_at: "2026-04-10T00:00:00Z",
};

const TICKETS_PAGE = {
  items: [
    {
      id: 1, project_id: 1, sprint_id: 10, assignee_id: 5, reporter_id: 3,
      title: "Task A", description: "", status: "done", priority: "high",
      ticket_type: "story", estimated_hours: 4, actual_hours: null,
      story_points: 3, quality_score: 80,
      last_activity_at: new Date(Date.now() - 2 * 3_600_000).toISOString(),
      created_at: "2026-04-01T00:00:00Z", updated_at: "2026-04-08T00:00:00Z",
    },
    {
      id: 2, project_id: 1, sprint_id: 10, assignee_id: 6, reporter_id: 3,
      title: "Task B", description: "", status: "blocked", priority: "medium",
      ticket_type: "bug", estimated_hours: 2, actual_hours: null,
      story_points: 2, quality_score: 60,
      last_activity_at: new Date(Date.now() - 30 * 3_600_000).toISOString(),
      created_at: "2026-04-02T00:00:00Z", updated_at: "2026-04-09T00:00:00Z",
    },
  ],
  total: 2,
  page: 1,
  page_size: 200,
};

const KPI_DASH = {
  project_id: 1,
  sprint_id: 10,
  current_kpis: {
    id: 1, project_id: 1, sprint_id: 10,
    cycle_time_hours: 24, lead_time_hours: 48, velocity: 38,
    completion_rate: 0.84, estimation_accuracy: 0.82,
    throughput: 1.5, bug_rate: 0.15,
    computed_at: "2026-04-10T18:00:00Z",
  },
  velocity_trend: [30, 35, 38],
  completion_trend: [0.75, 0.80, 0.84],
  open_blockers: 2,
  stalled_tickets: 1,
  repo_mismatches: 3,
};

const BURNDOWN_CHART = {
  sprint_id: 10,
  sprint_name: "PHX-S2",
  start_date: "2026-04-03",
  end_date: "2026-04-17",
  committed_points: 40,
  entries: [
    { id: 1, sprint_id: 10, date: "2026-04-03", remaining_points: 40, completed_points: 0, ideal_remaining: 40, cumulative_completed: 0 },
    { id: 2, sprint_id: 10, date: "2026-04-04", remaining_points: 35, completed_points: 5, ideal_remaining: 37.1, cumulative_completed: 5 },
  ],
};

const VELOCITY = [
  { sprint: "PHX-S1", points: 30 },
  { sprint: "PHX-S2", points: 38 },
];

const BLOCKERS = [
  {
    id: 7, ticket_id: 2, description: "No commits", stall_hours: 30,
    escalation_level: 2 as const,
    detected_at: new Date(Date.now() - 5 * 3_600_000).toISOString(),
    last_escalated_at: null, resolved_at: null,
    created_at: "2026-04-08T00:00:00Z", updated_at: "2026-04-09T00:00:00Z",
    ticket_title: "Task B", ticket_assignee_id: 6,
  },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

/** Build a fetch mock that matches URL patterns → JSON responses */
function mockFetch(handlers: Array<[RegExp | string, unknown]>) {
  return vi.fn((url: string) => {
    for (const [pattern, data] of handlers) {
      const match =
        typeof pattern === "string" ? url.includes(pattern) : pattern.test(url);
      if (match) {
        return Promise.resolve({
          ok: true,
          status: 200,
          statusText: "OK",
          headers: { get: () => null },
          json: () => Promise.resolve(data),
        });
      }
    }
    return Promise.resolve({
      ok: false,
      status: 404,
      statusText: "Not Found",
      headers: { get: () => null },
      json: () => Promise.resolve({ detail: "Not found" }),
    });
  });
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("useCurrentSprint", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch([
        [/\/projects\/1\/sprints\/current/, SPRINT],
        [/\/tickets\?project_id=1/, TICKETS_PAGE],
      ]),
    );
  });
  afterEach(() => vi.restoreAllMocks());

  it("returns data after successful fetch", async () => {
    const { result } = renderHook(() => useCurrentSprint(1), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.isError).toBe(false);
    expect(result.current.data?.name).toBe("PHX-S2");
    expect(result.current.data?.totalTickets).toBe(2);
    expect(result.current.data?.completedTickets).toBe(1);
    expect(result.current.data?.blockedTickets).toBe(1);
  });

  it("stays in loading state while fetches are pending", () => {
    const { result } = renderHook(() => useCurrentSprint(1), {
      wrapper: makeWrapper(),
    });
    expect(result.current.isLoading).toBe(true);
  });

  it("does not fetch when projectId is 0", () => {
    renderHook(() => useCurrentSprint(0), { wrapper: makeWrapper() });
    const fetchMock = vi.mocked(global.fetch);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("reports isError on network failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("Network error"))),
    );
    const { result } = renderHook(() => useCurrentSprint(1), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isError).toBe(true);
  });
});

describe("useSprintKpis", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch([[/\/kpis\?project_id=1/, KPI_DASH]]),
    );
  });
  afterEach(() => vi.restoreAllMocks());

  it("returns adapted KPI data", async () => {
    const { result } = renderHook(() => useSprintKpis(1), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data?.velocity.value).toBe("38");
    expect(result.current.data?.blockedCount.value).toBe(2);
    expect(result.current.data?.completionRate.value).toBe("84%");
  });

  it("does not fetch when projectId is 0", () => {
    renderHook(() => useSprintKpis(0), { wrapper: makeWrapper() });
    expect(vi.mocked(global.fetch)).not.toHaveBeenCalled();
  });
});

describe("useBurndown", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch([
        [/\/projects\/1\/sprints\/current/, SPRINT],
        [/\/sprints\/10\/burndown/, BURNDOWN_CHART],
      ]),
    );
  });
  afterEach(() => vi.restoreAllMocks());

  it("returns burndown points", async () => {
    const { result } = renderHook(() => useBurndown(1), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data).toHaveLength(2);
    expect(result.current.data?.[0].day).toBe("2026-04-03");
    expect(result.current.data?.[0].actual).toBe(40);
  });
});

describe("useVelocityHistory", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch([[/\/projects\/1\/sprints\/velocity/, VELOCITY]]),
    );
  });
  afterEach(() => vi.restoreAllMocks());

  it("returns velocity data array", async () => {
    const { result } = renderHook(() => useVelocityHistory(1), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data).toHaveLength(2);
    expect(result.current.data?.[0].sprint).toBe("PHX-S1");
  });
});

describe("useBlockers", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch([[/\/blockers\?project_id=1/, BLOCKERS]]),
    );
  });
  afterEach(() => vi.restoreAllMocks());

  it("returns adapted blockers", async () => {
    const { result } = renderHook(() => useBlockers(1), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].ticketId).toBe("T-2");
    expect(result.current.data?.[0].escalationLevel).toBe(2);
  });
});

describe("useTickets", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch([[/\/tickets\?project_id=1/, TICKETS_PAGE]]),
    );
  });
  afterEach(() => vi.restoreAllMocks());

  it("returns adapted UI tickets", async () => {
    const { result } = renderHook(() => useTickets(1), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data).toHaveLength(2);
    expect(result.current.data?.[0].id).toBe("T-1");
    expect(result.current.data?.[0].status).toBe("completed");
    expect(result.current.data?.[1].status).toBe("blocked");
  });
});

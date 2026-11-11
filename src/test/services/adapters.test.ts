/**
 * Unit tests for API adapter/transformer functions.
 * These are pure functions — no network, no DOM.
 */
import { describe, it, expect } from "vitest";
import { adaptTicket, adaptBlocker } from "@/services/api/tickets";
import { adaptDeveloper, adaptRepositoryMismatch } from "@/services/api/developers";
import { adaptSprint, adaptBurndown, adaptKpis } from "@/services/api/sprints";
import type {
  BackendTicket,
  BackendBlocker,
  BackendDeveloper,
  BackendRepositoryMismatch,
  BackendSprint,
  BackendBurndownChart,
  BackendKPIDashboard,
} from "@/services/api/types";

// ── Helpers ───────────────────────────────────────────────────────────────────

const makeTicket = (overrides: Partial<BackendTicket> = {}): BackendTicket => ({
  id: 42,
  project_id: 1,
  sprint_id: 10,
  assignee_id: 5,
  reporter_id: 3,
  title: "Fix critical auth bug",
  description: "Detailed description here",
  status: "in_progress",
  priority: "high",
  ticket_type: "bug",
  estimated_hours: 8,
  actual_hours: null,
  story_points: 3,
  quality_score: 80,
  last_activity_at: new Date(Date.now() - 10 * 3_600_000).toISOString(), // 10h ago
  created_at: "2026-04-01T09:00:00Z",
  updated_at: "2026-04-05T14:00:00Z",
  ...overrides,
});

const makeBlocker = (overrides: Partial<BackendBlocker> = {}): BackendBlocker => ({
  id: 7,
  ticket_id: 42,
  description: "No commits found for 36h",
  stall_hours: 36.5,
  escalation_level: 2,
  detected_at: new Date(Date.now() - 5 * 3_600_000).toISOString(),
  last_escalated_at: null,
  resolved_at: null,
  created_at: "2026-04-08T08:00:00Z",
  updated_at: "2026-04-09T10:00:00Z",
  ticket_title: "Fix critical auth bug",
  ticket_assignee_id: 5,
  ...overrides,
});

const makeDeveloper = (overrides: Partial<BackendDeveloper> = {}): BackendDeveloper => ({
  id: 5,
  name: "Alice Chen",
  email: "alice@acme.com",
  username: "alice",
  team: "Backend",
  role: "developer",
  slack_id: null,
  github_username: "alice-chen",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-04-01T00:00:00Z",
  ...overrides,
});

const makeSprint = (overrides: Partial<BackendSprint> = {}): BackendSprint => ({
  id: 10,
  project_id: 1,
  name: "PHX-S2: Acceleration",
  goal: "Deliver core features",
  start_date: "2026-04-03",
  end_date: "2026-04-17",
  status: "active",
  committed_points: 45,
  completed_points: 20,
  velocity: 20,
  created_at: "2026-04-03T00:00:00Z",
  updated_at: "2026-04-10T00:00:00Z",
  ...overrides,
});

// ── adaptTicket ───────────────────────────────────────────────────────────────

describe("adaptTicket", () => {
  it("maps id to T-{id} string", () => {
    const result = adaptTicket(makeTicket({ id: 42 }));
    expect(result.id).toBe("T-42");
    expect(result.numericId).toBe(42);
  });

  it("maps in_progress → in-progress", () => {
    expect(adaptTicket(makeTicket({ status: "in_progress" })).status).toBe("in-progress");
  });

  it("maps in_review → in-progress", () => {
    expect(adaptTicket(makeTicket({ status: "in_review" })).status).toBe("in-progress");
  });

  it("maps done → completed", () => {
    expect(adaptTicket(makeTicket({ status: "done" })).status).toBe("completed");
  });

  it("maps backlog → not-started", () => {
    expect(adaptTicket(makeTicket({ status: "backlog" })).status).toBe("not-started");
  });

  it("maps todo → not-started", () => {
    expect(adaptTicket(makeTicket({ status: "todo" })).status).toBe("not-started");
  });

  it("preserves blocked status", () => {
    expect(adaptTicket(makeTicket({ status: "blocked" })).status).toBe("blocked");
  });

  it("maps critical priority", () => {
    expect(adaptTicket(makeTicket({ priority: "critical" })).priority).toBe("critical");
  });

  it("maps high priority", () => {
    expect(adaptTicket(makeTicket({ priority: "high" })).priority).toBe("high");
  });

  it("uses 0 when story_points is null", () => {
    expect(adaptTicket(makeTicket({ story_points: null })).storyPoints).toBe(0);
  });

  it("uses 0 when quality_score is null", () => {
    expect(adaptTicket(makeTicket({ quality_score: null })).qualityScore).toBe(0);
  });

  it("sets stalledHours when last activity > 24h ago", () => {
    const old = new Date(Date.now() - 30 * 3_600_000).toISOString();
    const result = adaptTicket(makeTicket({ last_activity_at: old }));
    expect(result.stalledHours).toBeGreaterThan(24);
  });

  it("stalledHours is undefined when activity < 24h ago", () => {
    const recent = new Date(Date.now() - 5 * 3_600_000).toISOString();
    const result = adaptTicket(makeTicket({ last_activity_at: recent }));
    expect(result.stalledHours).toBeUndefined();
  });

  it("uses ticket_type as label", () => {
    expect(adaptTicket(makeTicket({ ticket_type: "story" })).labels).toContain("story");
  });
});

// ── adaptBlocker ──────────────────────────────────────────────────────────────

describe("adaptBlocker", () => {
  it("formats ticketId as T-{id}", () => {
    expect(adaptBlocker(makeBlocker({ ticket_id: 42 })).ticketId).toBe("T-42");
  });

  it("rounds stall_hours", () => {
    expect(adaptBlocker(makeBlocker({ stall_hours: 36.7 })).stalledHours).toBe(37);
  });

  it("uses ticket_title when available", () => {
    const b = adaptBlocker(makeBlocker({ ticket_title: "My Title" }));
    expect(b.title).toBe("My Title");
  });

  it("falls back to Ticket #{id} when ticket_title absent", () => {
    const b = adaptBlocker(makeBlocker({ ticket_title: undefined }));
    expect(b.title).toMatch(/Ticket #42/);
  });

  it("sets management impact for level 3", () => {
    const b = adaptBlocker(makeBlocker({ escalation_level: 3 }));
    expect(b.impact).toMatch(/sprint goal/i);
  });

  it("sets team risk impact for level 2", () => {
    const b = adaptBlocker(makeBlocker({ escalation_level: 2 }));
    expect(b.impact).toMatch(/team/i);
  });

  it("preserves escalation level", () => {
    expect(adaptBlocker(makeBlocker({ escalation_level: 1 })).escalationLevel).toBe(1);
  });
});

// ── adaptDeveloper ────────────────────────────────────────────────────────────

describe("adaptDeveloper", () => {
  it("builds initials from name", () => {
    const d = adaptDeveloper(makeDeveloper({ name: "Alice Chen" }));
    expect(d.avatar).toBe("AC");
  });

  it("handles single-word name", () => {
    const d = adaptDeveloper(makeDeveloper({ name: "Cher" }));
    expect(d.avatar).toBe("C");
  });

  it("preserves id and name", () => {
    const d = adaptDeveloper(makeDeveloper({ id: 99, name: "Bob Martinez" }));
    expect(d.id).toBe(99);
    expect(d.name).toBe("Bob Martinez");
  });

  it("defaults to on-track status", () => {
    expect(adaptDeveloper(makeDeveloper()).status).toBe("on-track");
  });

  it("preserves role", () => {
    expect(adaptDeveloper(makeDeveloper({ role: "team_lead" })).role).toBe("team_lead");
  });
});

// ── adaptRepositoryMismatch ───────────────────────────────────────────────────

describe("adaptRepositoryMismatch", () => {
  const makeRM = (o: Partial<BackendRepositoryMismatch> = {}): BackendRepositoryMismatch => ({
    id: 1,
    ticket_id: 42,
    project_id: 1,
    branch_name: "feature/42-fix-auth",
    commit_count: 0,
    pr_count: 0,
    pr_merged: false,
    last_commit_at: null,
    mismatch_type: "no_commits_in_progress",
    mismatch_reason: "Ticket in-progress but no commits.",
    scanned_at: "2026-04-10T00:00:00Z",
    ...o,
  });

  it("formats ticket ref as T-{id}", () => {
    expect(adaptRepositoryMismatch(makeRM({ ticket_id: 42 })).ticket).toBe("T-42");
  });

  it("sets prStatus=merged when pr_merged=true", () => {
    expect(adaptRepositoryMismatch(makeRM({ pr_merged: true, pr_count: 1 })).prStatus).toBe("merged");
  });

  it("sets prStatus=none when no PRs", () => {
    expect(adaptRepositoryMismatch(makeRM({ pr_count: 0 })).prStatus).toBe("none");
  });

  it("sets mismatch=true when mismatch_type is set", () => {
    expect(adaptRepositoryMismatch(makeRM({ mismatch_type: "stale_branch" })).mismatch).toBe(true);
  });

  it("sets mismatch=false when mismatch_type is null", () => {
    expect(adaptRepositoryMismatch(makeRM({ mismatch_type: null })).mismatch).toBe(false);
  });

  it("uses branch_name or falls back to feature/{id}", () => {
    const r = adaptRepositoryMismatch(makeRM({ branch_name: null, ticket_id: 99 }));
    expect(r.branch).toBe("feature/99");
  });

  it("formats lastCommit as date string", () => {
    const r = adaptRepositoryMismatch(makeRM({ last_commit_at: "2026-04-08T10:00:00Z" }));
    expect(r.lastCommit).toMatch(/\d{1,2}\/\d{1,2}\/\d{4}/);
  });

  it("uses Never when no last_commit_at", () => {
    const r = adaptRepositoryMismatch(makeRM({ last_commit_at: null }));
    expect(r.lastCommit).toBe("Never");
  });
});

// ── adaptSprint ───────────────────────────────────────────────────────────────

describe("adaptSprint", () => {
  it("sets totalTickets from tickets array length", () => {
    const s = adaptSprint(makeSprint(), [
      makeTicket({ status: "done" }),
      makeTicket({ status: "in_progress" }),
    ]);
    expect(s.totalTickets).toBe(2);
  });

  it("counts done tickets as completedTickets", () => {
    const s = adaptSprint(makeSprint(), [
      makeTicket({ status: "done" }),
      makeTicket({ status: "done" }),
      makeTicket({ status: "blocked" }),
    ]);
    expect(s.completedTickets).toBe(2);
    expect(s.blockedTickets).toBe(1);
  });

  it("counts in_progress and in_review as inProgressTickets", () => {
    const s = adaptSprint(makeSprint(), [
      makeTicket({ status: "in_progress" }),
      makeTicket({ status: "in_review" }),
      makeTicket({ status: "todo" }),
    ]);
    expect(s.inProgressTickets).toBe(2);
    expect(s.notStartedTickets).toBe(1);
  });

  it("preserves sprint name and id", () => {
    const s = adaptSprint(makeSprint({ id: 55, name: "Sprint 55" }), []);
    expect(s.id).toBe(55);
    expect(s.name).toBe("Sprint 55");
  });

  it("calculates positive daysRemaining for future end date", () => {
    const future = new Date(Date.now() + 7 * 86_400_000).toISOString().split("T")[0];
    const s = adaptSprint(makeSprint({ end_date: future }), []);
    expect(s.daysRemaining).toBeGreaterThan(0);
  });

  it("returns 0 daysRemaining for past end date", () => {
    const past = "2020-01-01";
    const s = adaptSprint(makeSprint({ end_date: past }), []);
    expect(s.daysRemaining).toBe(0);
  });
});

// ── adaptBurndown ─────────────────────────────────────────────────────────────

describe("adaptBurndown", () => {
  const chart: BackendBurndownChart = {
    sprint_id: 10,
    sprint_name: "S1",
    start_date: "2026-04-03",
    end_date: "2026-04-17",
    committed_points: 45,
    entries: [
      { id: 1, sprint_id: 10, date: "2026-04-03", remaining_points: 45, completed_points: 0, ideal_remaining: 45.0, cumulative_completed: 0 },
      { id: 2, sprint_id: 10, date: "2026-04-04", remaining_points: 40, completed_points: 5, ideal_remaining: 41.8, cumulative_completed: 5 },
    ],
  };

  it("maps each entry to a BurndownPoint", () => {
    const pts = adaptBurndown(chart);
    expect(pts).toHaveLength(2);
  });

  it("uses date as day key", () => {
    const pts = adaptBurndown(chart);
    expect(pts[0].day).toBe("2026-04-03");
  });

  it("maps remaining_points → actual", () => {
    const pts = adaptBurndown(chart);
    expect(pts[0].actual).toBe(45);
    expect(pts[1].actual).toBe(40);
  });

  it("maps ideal_remaining → ideal", () => {
    const pts = adaptBurndown(chart);
    expect(pts[0].ideal).toBe(45.0);
    expect(pts[1].ideal).toBeCloseTo(41.8, 1);
  });
});

// ── adaptKpis ─────────────────────────────────────────────────────────────────

describe("adaptKpis", () => {
  const makeDash = (overrides = {}): BackendKPIDashboard => ({
    project_id: 1,
    sprint_id: 10,
    current_kpis: {
      id: 1,
      project_id: 1,
      sprint_id: 10,
      cycle_time_hours: 24,
      lead_time_hours: 48,
      velocity: 38,
      completion_rate: 0.84,
      estimation_accuracy: 0.82,
      throughput: 1.5,
      bug_rate: 0.15,
      computed_at: "2026-04-10T18:00:00Z",
    },
    velocity_trend: [30, 35, 38],
    completion_trend: [0.75, 0.80, 0.84],
    open_blockers: 2,
    stalled_tickets: 1,
    repo_mismatches: 3,
    ...overrides,
  });

  it("formats cycle_time_hours as days", () => {
    const k = adaptKpis(makeDash());
    // 24h = 3d work day (24/8)
    expect(String(k.cycleTime.value)).toMatch(/d/);
  });

  it("formats completion_rate as percentage string", () => {
    const k = adaptKpis(makeDash());
    expect(String(k.completionRate.value)).toMatch(/84%/);
  });

  it("formats estimation_accuracy as percentage", () => {
    const k = adaptKpis(makeDash());
    expect(String(k.estimationAccuracy.value)).toMatch(/82%/);
  });

  it("shows open_blockers as blockedCount value", () => {
    const k = adaptKpis(makeDash());
    expect(k.blockedCount.value).toBe(2);
  });

  it("sets blockedCount type=positive when 0 blockers", () => {
    const k = adaptKpis(makeDash({ open_blockers: 0 } as Partial<BackendKPIDashboard>));
    expect(k.blockedCount.type).toBe("positive");
  });

  it("sets blockedCount type=negative when blockers exist", () => {
    const k = adaptKpis(makeDash({ open_blockers: 3 } as Partial<BackendKPIDashboard>));
    expect(k.blockedCount.type).toBe("negative");
  });

  it("handles null current_kpis gracefully", () => {
    const k = adaptKpis({ ...makeDash(), current_kpis: null });
    expect(k.cycleTime.value).toBe("N/A");
    expect(k.velocity.value).toBe("0");
  });

  it("sets velocity type positive when trending up", () => {
    // trend: [30, 35] => current is 38 (up from 35)
    const k = adaptKpis(makeDash());
    expect(k.velocity.type).toBe("positive");
  });
});

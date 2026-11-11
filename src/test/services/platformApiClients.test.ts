import { beforeEach, describe, expect, it, vi } from "vitest";
import { analyticsApi } from "@/services/api/analytics";
import { authApi } from "@/services/api/auth";
import { companyApi } from "@/services/api/companies";
import { developerApi } from "@/services/api/developers";
import { engagementApi } from "@/services/api/engagements";
import { trelloApi } from "@/services/api/trello";

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    status,
    ok: status >= 200 && status < 300,
    statusText: "OK",
    headers: { get: () => null },
    json: vi.fn().mockResolvedValue(body),
  });
}

describe("platform-aware API clients", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.setItem("kpimaster.authToken", "test-token");
  });

  it("adds provider to analytics responsiveness requests", async () => {
    const fetch = mockFetch(200, { developers: [], trend: [] });
    global.fetch = fetch;

    await analyticsApi.getResponsiveness(7, "2026-04-01", "2026-04-30", "github");

    const [url, init] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/analytics/responsiveness?");
    expect(url).toContain("project_id=7");
    expect(url).toContain("start_date=2026-04-01");
    expect(url).toContain("end_date=2026-04-30");
    expect(url).toContain("provider=github");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer test-token");
  });

  it("skips provider when platform is all", async () => {
    const fetch = mockFetch(200, { developers: [], trend: [] });
    global.fetch = fetch;

    await analyticsApi.getVendorDevelopers(3, undefined, undefined, "all");

    const [url] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/analytics/vendor/developers?project_id=3");
    expect(url).not.toContain("provider=");
  });

  it("includes sprint and provider in personal analytics requests", async () => {
    const fetch = mockFetch(200, { developer_id: 1 });
    global.fetch = fetch;

    await analyticsApi.getDeveloperMe(8, 12, "2026-04-01", "2026-04-30", "jira");

    const [url] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/analytics/developer/me?");
    expect(url).toContain("project_id=8");
    expect(url).toContain("sprint_id=12");
    expect(url).toContain("provider=jira");
  });

  it("maps repository mismatches and passes github provider", async () => {
    const fetch = mockFetch(200, [
      {
        id: 1,
        ticket_id: 42,
        project_id: 5,
        branch_name: null,
        commit_count: 0,
        pr_count: 1,
        pr_merged: false,
        last_commit_at: null,
        mismatch_type: "no_commits_in_progress",
        mismatch_reason: "No commits",
        scanned_at: "2026-04-01T00:00:00Z",
      },
    ]);
    global.fetch = fetch;

    const result = await developerApi.getRepositoryMismatches(5, "2026-04-01", "2026-04-30", "github");

    const [url] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/repository-mismatches?");
    expect(url).toContain("provider=github");
    expect(result[0]).toMatchObject({
      ticket: "T-42",
      branch: "feature/42",
      prStatus: "open",
      mismatch: true,
    });
  });

  it("passes provider through KPI endpoints", async () => {
    const fetch = mockFetch(200, {});
    global.fetch = fetch;

    await developerApi.getTeamKPIs(9, 4, "2026-04-01", "2026-04-30", "trello");
    await developerApi.getClientProgress(9, undefined, "2026-04-01", "2026-04-30", "microsoft");
    await developerApi.getDeveloperKPIs(11, 9, 4, "2026-04-01", "2026-04-30", "jira");

    const urls = fetch.mock.calls.map((call) => call[0] as string);
    expect(urls[0]).toContain("/developers/team-kpis?");
    expect(urls[0]).toContain("provider=trello");
    expect(urls[1]).toContain("/developers/client-progress?");
    expect(urls[1]).toContain("provider=microsoft");
    expect(urls[2]).toContain("/developers/11/kpis?");
    expect(urls[2]).toContain("provider=jira");
  });

  it("covers auth API methods", async () => {
    const fetch = mockFetch(200, { access_token: "jwt" });
    global.fetch = fetch;

    await authApi.login({ username: "alice", password: "secret" });
    await authApi.register({ username: "bob", email: "bob@example.com", password: "secret" });
    await authApi.me();

    expect(fetch.mock.calls[0][0]).toContain("/auth/login");
    expect((fetch.mock.calls[0][1] as RequestInit).method).toBe("POST");
    expect((fetch.mock.calls[0][1] as RequestInit).body).toBe(JSON.stringify({ username: "alice", password: "secret" }));
    expect(fetch.mock.calls[1][0]).toContain("/auth/register");
    expect(fetch.mock.calls[2][0]).toContain("/auth/me");
  });

  it("covers company API endpoints", async () => {
    const fetch = mockFetch(200, {});
    global.fetch = fetch;

    await companyApi.getAll("vendor");
    await companyApi.getMine();
    await companyApi.updateMine({ name: "Norma", description: "Desc" });
    await companyApi.getPartnerships();
    await companyApi.createPartnership(14);

    const urls = fetch.mock.calls.map((call) => call[0] as string);
    expect(urls[0]).toContain("/companies?tenant_type=vendor");
    expect(urls[1]).toContain("/companies/me");
    expect((fetch.mock.calls[2][1] as RequestInit).method).toBe("PATCH");
    expect((fetch.mock.calls[2][1] as RequestInit).body).toBe(JSON.stringify({ name: "Norma", description: "Desc" }));
    expect(urls[3]).toContain("/companies/me/partnerships");
    expect((fetch.mock.calls[4][1] as RequestInit).body).toBe(JSON.stringify({ vendor_company_id: 14 }));
  });

  it("covers engagement API endpoints", async () => {
    const fetch = mockFetch(200, []);
    global.fetch = fetch;

    await engagementApi.list(6);
    await engagementApi.create({
      name: "Delivery",
      status: "active",
      vendor_company_id: 4,
      project_id: 6,
      client_visible: true,
    });
    await engagementApi.listAssignments(15);
    await engagementApi.createAssignment(15, {
      developer_id: 2,
      assignment_role: "developer",
      status: "active",
      allocation_percentage: 50,
    });

    expect(fetch.mock.calls[0][0]).toContain("/engagements?project_id=6");
    expect(fetch.mock.calls[1][0]).toContain("/engagements");
    expect((fetch.mock.calls[1][1] as RequestInit).method).toBe("POST");
    expect(fetch.mock.calls[2][0]).toContain("/engagements/15/assignments");
    expect((fetch.mock.calls[3][1] as RequestInit).body).toContain("\"allocation_percentage\":50");
  });

  it("covers trello API endpoints and payload shaping", async () => {
    const fetch = mockFetch(200, {});
    global.fetch = fetch;

    await trelloApi.getSettings();
    await trelloApi.saveSettings({ apiKey: "", apiToken: "", selectedBoardIds: ["a"] });
    await trelloApi.listAvailableBoards({ apiKey: "key", apiToken: "token", boardIds: ["b1"] });
    await trelloApi.importBoards({ apiKey: "key", apiToken: "token", boardIds: ["b1", "b2"] });
    await trelloApi.syncProject(4, true);
    await trelloApi.getProjectBoardSummary(4, "2026-04-01", "2026-04-30");
    await trelloApi.reclassifyBoardLists(22);

    expect(fetch.mock.calls[0][0]).toContain("/trello/settings");
    expect((fetch.mock.calls[1][1] as RequestInit).body).toBe(JSON.stringify({
      api_key: null,
      api_token: null,
      selected_board_ids: ["a"],
    }));
    expect((fetch.mock.calls[2][1] as RequestInit).body).toContain("\"board_ids\":[\"b1\"]");
    expect(fetch.mock.calls[4][0]).toContain("/trello/projects/4/sync?full=true");
    expect(fetch.mock.calls[5][0]).toContain("/trello/projects/4/board-summary?start_date=2026-04-01&end_date=2026-04-30");
    expect(fetch.mock.calls[6][0]).toContain("/trello/boards/22/reclassify-lists");
  });
});

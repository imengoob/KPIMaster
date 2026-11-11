/**
 * Unit tests for integrations API client.
 *
 * All network calls are intercepted by replacing `global.fetch` with a spy
 * so no real backend is needed.
 *
 * Coverage:
 *   listAccounts      — GET /integrations
 *   disconnect        — DELETE /integrations/{id}   (handles 204 No Content)
 *   getHealth         — GET /integrations/{id}/health
 *   listBoards        — GET /integrations/{id}/boards
 *   listTasks         — GET /integrations/{id}/tasks
 *   triggerSync       — POST /integrations/{id}/sync
 *   getSyncLogs       — GET /integrations/{id}/sync-logs
 *   connectTrello     — POST /integrations/connect/trello
 *   connectGitHub     — POST /integrations/connect/github
 *   startJiraOAuth    — GET /integrations/oauth/jira/start
 *   startMicrosoftOAuth — GET /integrations/oauth/microsoft/start
 *   Error paths       — 4xx / 5xx responses
 */
import { beforeEach, describe, expect, it, vi, type MockedFunction } from "vitest";
import { integrationApi } from "@/services/api/integrations";
import type { IntegrationAccount } from "@/services/api/integrations";

// ── Fake data factories ────────────────────────────────────────────────────

const fakeAccount = (overrides: Partial<IntegrationAccount> = {}): IntegrationAccount => ({
  id: 1,
  user_id: 10,
  provider: "trello",
  account_name: "My Trello",
  external_account_id: "member_abc",
  is_active: true,
  last_sync_at: null,
  token_expires_at: null,
  scopes: [],
  extra_data: {},
  created_at: "2026-04-01T00:00:00Z",
  updated_at: "2026-04-10T00:00:00Z",
  ...overrides,
});

const fakeBoard = () => ({
  id: "board-1",
  name: "Sprint Board",
  provider: "trello" as const,
  url: "https://trello.com/b/board-1",
  is_active: true,
  extra: {},
});

const fakeOAuthInit = (provider: "jira" | "microsoft") => ({
  authorization_url: `https://auth.${provider}.example.com/authorize?client_id=cid`,
  state: "csrf-state-token",
  provider,
});

// ── Fetch mock helpers ─────────────────────────────────────────────────────

function mockFetch(status: number, body: unknown, headers: Record<string, string> = {}) {
  return vi.fn().mockResolvedValue({
    status,
    ok: status >= 200 && status < 300,
    statusText: status === 204 ? "No Content" : "OK",
    headers: {
      get: (key: string) => {
        if (key === "content-length" && status === 204) return "0";
        return headers[key] ?? null;
      },
    },
    json: vi.fn().mockResolvedValue(body),
  });
}

beforeEach(() => {
  // Reset auth token
  localStorage.setItem("kpimaster.authToken", "test-jwt-token");
  vi.restoreAllMocks();
});

// ── listAccounts ───────────────────────────────────────────────────────────

describe("listAccounts", () => {
  it("calls GET /integrations", async () => {
    const fetch = mockFetch(200, [fakeAccount()]);
    global.fetch = fetch;

    await integrationApi.listAccounts();

    const [url] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/integrations");
    expect(fetch.mock.calls[0][1]?.method).toBeUndefined(); // defaults to GET
  });

  it("passes provider filter as query param", async () => {
    const fetch = mockFetch(200, []);
    global.fetch = fetch;

    await integrationApi.listAccounts("jira");

    const [url] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("provider=jira");
  });

  it("returns parsed array of accounts", async () => {
    global.fetch = mockFetch(200, [fakeAccount(), fakeAccount({ id: 2 })]);
    const result = await integrationApi.listAccounts();
    expect(result).toHaveLength(2);
    expect(result[0].provider).toBe("trello");
  });

  it("sends Bearer token from localStorage", async () => {
    const fetch = mockFetch(200, []);
    global.fetch = fetch;

    await integrationApi.listAccounts();

    const [, init] = fetch.mock.calls[0] as [string, RequestInit];
    const headers = init?.headers as Record<string, string>;
    expect(headers?.["Authorization"]).toBe("Bearer test-jwt-token");
  });
});

// ── disconnect ─────────────────────────────────────────────────────────────

describe("disconnect", () => {
  it("calls DELETE /integrations/{id}", async () => {
    const fetch = mockFetch(204, null);
    global.fetch = fetch;

    await integrationApi.disconnect(42);

    const [url, init] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/integrations/42");
    expect(init?.method).toBe("DELETE");
  });

  it("resolves without error on 204 No Content", async () => {
    global.fetch = mockFetch(204, null);
    await expect(integrationApi.disconnect(1)).resolves.toBeUndefined();
  });

  it("throws ApiError on 404", async () => {
    global.fetch = mockFetch(404, { detail: "Not found" });
    await expect(integrationApi.disconnect(9999)).rejects.toThrow();
  });
});

// ── getHealth ──────────────────────────────────────────────────────────────

describe("getHealth", () => {
  it("calls GET /integrations/{id}/health", async () => {
    const health = {
      account_id: 1, provider: "trello", account_name: "Test",
      is_active: true, credentials_ok: true, last_sync_at: null, token_expires_at: null,
    };
    const fetch = mockFetch(200, health);
    global.fetch = fetch;

    const result = await integrationApi.getHealth(1);

    const [url] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/integrations/1/health");
    expect(result.credentials_ok).toBe(true);
  });
});

// ── listBoards ─────────────────────────────────────────────────────────────

describe("listBoards", () => {
  it("calls GET /integrations/{id}/boards", async () => {
    const fetch = mockFetch(200, [fakeBoard()]);
    global.fetch = fetch;

    const boards = await integrationApi.listBoards(5);

    const [url] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/integrations/5/boards");
    expect(boards).toHaveLength(1);
    expect(boards[0].name).toBe("Sprint Board");
  });

  it("returns empty array when no boards", async () => {
    global.fetch = mockFetch(200, []);
    expect(await integrationApi.listBoards(1)).toEqual([]);
  });
});

// ── listTasks ──────────────────────────────────────────────────────────────

describe("listTasks", () => {
  it("calls GET /integrations/{id}/tasks?board_id=...", async () => {
    const fetch = mockFetch(200, []);
    global.fetch = fetch;

    await integrationApi.listTasks(3, "board-abc");

    const [url] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/integrations/3/tasks");
    expect(url).toContain("board_id=board-abc");
  });

  it("URL-encodes board_id with special characters", async () => {
    const fetch = mockFetch(200, []);
    global.fetch = fetch;

    await integrationApi.listTasks(1, "board/with spaces");

    const [url] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).not.toContain(" ");
  });
});

// ── triggerSync ────────────────────────────────────────────────────────────

describe("triggerSync", () => {
  it("calls POST /integrations/{id}/sync", async () => {
    const fetch = mockFetch(200, {
      account_id: 1, board_id: "b1", provider: "trello", synced: 5, incremental: true,
    });
    global.fetch = fetch;

    await integrationApi.triggerSync(1, "b1");

    const [url, init] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/integrations/1/sync");
    expect(init?.method).toBe("POST");
  });

  it("passes full=true when requested", async () => {
    const fetch = mockFetch(200, {
      account_id: 1, board_id: "b1", provider: "trello", synced: 10, incremental: false,
    });
    global.fetch = fetch;

    await integrationApi.triggerSync(1, "b1", true);

    const [url] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("full=true");
  });

  it("passes project_id when syncing into a project", async () => {
    const fetch = mockFetch(200, {
      account_id: 1, board_id: "b1", provider: "github", synced: 10, incremental: false,
    });
    global.fetch = fetch;

    await integrationApi.triggerSync(1, "repo/octo", true, 42);

    const [url] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("board_id=repo%2Focto");
    expect(url).toContain("project_id=42");
  });

  it("returns sync result with synced count", async () => {
    global.fetch = mockFetch(200, {
      account_id: 1, board_id: "b1", provider: "trello", synced: 12, incremental: true,
    });
    const result = await integrationApi.triggerSync(1, "b1");
    expect(result.synced).toBe(12);
  });
});

// ── getSyncLogs ────────────────────────────────────────────────────────────

describe("getSyncLogs", () => {
  it("calls GET /integrations/{id}/sync-logs with limit param", async () => {
    const fetch = mockFetch(200, []);
    global.fetch = fetch;

    await integrationApi.getSyncLogs(7, 5);

    const [url] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/integrations/7/sync-logs");
    expect(url).toContain("limit=5");
  });
});

// ── importBoard ────────────────────────────────────────────────────────────

describe("importBoard", () => {
  it("calls POST /integrations/{id}/import-board with encoded board_id", async () => {
    const fetch = mockFetch(200, {
      project_id: 42,
      project_key: "ENG",
      board_id: "owner/repo",
      board_name: "owner/repo",
    });
    global.fetch = fetch;

    const result = await integrationApi.importBoard(7, "owner/repo");

    const [url, init] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/integrations/7/import-board");
    expect(url).toContain("board_id=owner%2Frepo");
    expect(init?.method).toBe("POST");
    expect(result.project_key).toBe("ENG");
  });
});

// ── connectTrello ──────────────────────────────────────────────────────────

describe("connectTrello", () => {
  it("calls POST /integrations/connect/trello", async () => {
    const fetch = mockFetch(201, fakeAccount());
    global.fetch = fetch;

    await integrationApi.connectTrello("my-key", "my-token", "Work Trello");

    const [url, init] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/integrations/connect/trello");
    expect(init?.method).toBe("POST");
  });

  it("sends api_key, api_token, label in body", async () => {
    const fetch = mockFetch(201, fakeAccount());
    global.fetch = fetch;

    await integrationApi.connectTrello("key123", "tok456", "My Label");

    const [, init] = fetch.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init?.body as string);
    expect(body.api_key).toBe("key123");
    expect(body.api_token).toBe("tok456");
    expect(body.label).toBe("My Label");
  });

  it("returns the created account", async () => {
    const account = fakeAccount({ provider: "trello", account_name: "Work Trello" });
    global.fetch = mockFetch(201, account);

    const result = await integrationApi.connectTrello("k", "t", "Work Trello");
    expect(result.account_name).toBe("Work Trello");
  });
});

// ── connectGitHub ──────────────────────────────────────────────────────────

describe("connectGitHub", () => {
  it("calls POST /integrations/connect/github", async () => {
    const fetch = mockFetch(201, fakeAccount({ provider: "github" }));
    global.fetch = fetch;

    await integrationApi.connectGitHub("github_pat_test", "Work GitHub");

    const [url, init] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/integrations/connect/github");
    expect(init?.method).toBe("POST");
  });

  it("sends access_token and label in body", async () => {
    const fetch = mockFetch(201, fakeAccount({ provider: "github" }));
    global.fetch = fetch;

    await integrationApi.connectGitHub("gh-token", "Engineering GitHub");

    const [, init] = fetch.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init?.body as string);
    expect(body.access_token).toBe("gh-token");
    expect(body.label).toBe("Engineering GitHub");
  });
});

// ── startJiraOAuth ─────────────────────────────────────────────────────────

describe("startJiraOAuth", () => {
  it("calls GET /integrations/oauth/jira/start", async () => {
    const fetch = mockFetch(200, fakeOAuthInit("jira"));
    global.fetch = fetch;

    await integrationApi.startJiraOAuth();

    const [url] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/integrations/oauth/jira/start");
  });

  it("returns authorization_url, state, provider", async () => {
    global.fetch = mockFetch(200, fakeOAuthInit("jira"));
    const result = await integrationApi.startJiraOAuth();
    expect(result.authorization_url).toContain("auth.jira");
    expect(result.state).toBe("csrf-state-token");
    expect(result.provider).toBe("jira");
  });
});

// ── startMicrosoftOAuth ────────────────────────────────────────────────────

describe("startMicrosoftOAuth", () => {
  it("calls GET /integrations/oauth/microsoft/start", async () => {
    const fetch = mockFetch(200, fakeOAuthInit("microsoft"));
    global.fetch = fetch;

    await integrationApi.startMicrosoftOAuth();

    const [url] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/integrations/oauth/microsoft/start");
  });

  it("returns provider=microsoft", async () => {
    global.fetch = mockFetch(200, fakeOAuthInit("microsoft"));
    const result = await integrationApi.startMicrosoftOAuth();
    expect(result.provider).toBe("microsoft");
  });
});

// ── Error handling ─────────────────────────────────────────────────────────

describe("error handling", () => {
  it("throws on 500 server error", async () => {
    global.fetch = mockFetch(500, { detail: "Internal server error" });
    await expect(integrationApi.listAccounts()).rejects.toThrow();
  });

  it("throws on 503 not configured", async () => {
    global.fetch = mockFetch(503, { detail: "Jira OAuth not configured" });
    await expect(integrationApi.startJiraOAuth()).rejects.toThrow();
  });

  it("includes status code in thrown error", async () => {
    global.fetch = mockFetch(404, { detail: "Not found" });
    try {
      await integrationApi.disconnect(999);
    } catch (e: unknown) {
      expect(String(e)).toContain("404");
    }
  });
});

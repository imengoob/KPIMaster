import { beforeEach, describe, expect, it, vi } from "vitest";
import { actionApi } from "@/services/api/actions";

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    status,
    ok: status >= 200 && status < 300,
    statusText: "OK",
    headers: {
      get: () => null,
    },
    json: vi.fn().mockResolvedValue(body),
  });
}

beforeEach(() => {
  localStorage.setItem("kpimaster.authToken", "test-jwt-token");
  vi.restoreAllMocks();
});

describe("actionApi", () => {
  it("lists project actions with filters encoded as query params", async () => {
    const fetch = mockFetch(200, []);
    global.fetch = fetch;

    await actionApi.list({
      projectId: 7,
      status: "open",
      sourceType: "blocker",
      owner: "mine",
      includeResolved: true,
    });

    const [url, init] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/actions?");
    expect(url).toContain("project_id=7");
    expect(url).toContain("status=open");
    expect(url).toContain("source_type=blocker");
    expect(url).toContain("owner=mine");
    expect(url).toContain("include_resolved=true");
    expect(init?.method).toBeUndefined();
  });

  it("gets one action detail", async () => {
    const fetch = mockFetch(200, { id: 12, events: [] });
    global.fetch = fetch;

    const result = await actionApi.get(12);

    expect((fetch.mock.calls[0] as [string, RequestInit])[0]).toContain("/api/v1/actions/12");
    expect(result.id).toBe(12);
  });

  it("generates project actions", async () => {
    const fetch = mockFetch(200, { generated: 2, refreshed: 1, total_open: 3, action_ids: [1, 2] });
    global.fetch = fetch;

    await actionApi.generate(4);

    const [url, init] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/actions/generate?project_id=4");
    expect(init?.method).toBe("POST");
  });

  it("updates an action with a JSON body", async () => {
    const fetch = mockFetch(200, { id: 5, events: [] });
    global.fetch = fetch;

    await actionApi.update(5, { priority: "high", note: "Client demo blocker." });

    const [url, init] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/actions/5");
    expect(init?.method).toBe("PATCH");
    expect(init?.body).toBe(JSON.stringify({ priority: "high", note: "Client demo blocker." }));
  });

  it("transitions an action with an optional note", async () => {
    const fetch = mockFetch(200, { id: 5, status: "resolved", events: [] });
    global.fetch = fetch;

    await actionApi.transition(5, "resolve", "Ready for review.");

    const [url, init] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/actions/5/resolve");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ note: "Ready for review." }));
  });
});

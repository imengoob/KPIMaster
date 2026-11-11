import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useResponsivenessAnalytics } from "@/hooks/useResponsiveness";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

describe("useResponsivenessAnalytics", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve({
      ok: true,
      status: 200,
      statusText: "OK",
      headers: { get: () => null },
      json: () => Promise.resolve({
        project_id: 7,
        company_id: null,
        global_avg_reaction_hours: 1.5,
        global_avg_response_hours: 2.5,
        total_developer_comments: 4,
        total_developer_reactions: 6,
        active_developers: 1,
        dormant_developers: 0,
        total_sla_breaches: 0,
        trend: [],
        developers: [],
        requested_url: url,
      }),
    })));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches responsiveness metrics with provider filters", async () => {
    const { result } = renderHook(
      () => useResponsivenessAnalytics(7, "2026-04-01", "2026-04-30", "github"),
      { wrapper: makeWrapper() },
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data?.global_avg_reaction_hours).toBe(1.5);

    const fetchMock = vi.mocked(global.fetch);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toContain("provider=github");
  });

  it("does not fetch when project id is missing", () => {
    renderHook(() => useResponsivenessAnalytics(undefined), {
      wrapper: makeWrapper(),
    });

    expect(vi.mocked(global.fetch)).not.toHaveBeenCalled();
  });
});

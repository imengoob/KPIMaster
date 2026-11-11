/**
 * ProjectContext unit tests.
 * Tests the provider: fallback behavior, project loading, and switching.
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { act, render, screen, waitFor, fireEvent } from "@testing-library/react";
import { ProjectProvider, useProject } from "@/contexts/ProjectContext";

const BACKEND_PROJECTS = [
  { id: 10, name: "Alpha", key: "ALP", repository_url: "https://github.com/a/a", description: "", team_size: 5, created_at: "", updated_at: "" },
  { id: 11, name: "Beta",  key: "BET", repository_url: null, description: "", team_size: 3, created_at: "", updated_at: "" },
];

function mockFetchProjects(data: unknown) {
  return vi.fn(() =>
    Promise.resolve({
      ok: true,
      status: 200,
      statusText: "OK",
      headers: { get: () => null },
      json: () => Promise.resolve({ items: data, total: (data as unknown[]).length, page: 1, page_size: 100 }),
    }),
  );
}

/** Simple consumer component that exposes context values via data-testid */
function Consumer() {
  const {
    currentProject,
    allProjects,
    isLoadingProjects,
    refreshProjects,
    setCurrentProject,
    globalPlatformFilter,
    setGlobalPlatformFilter,
  } = useProject();
  return (
    <div>
      <span data-testid="current">{currentProject?.name ?? "none"}</span>
      <span data-testid="count">{allProjects.length}</span>
      <span data-testid="loading">{String(isLoadingProjects)}</span>
      <span data-testid="platform">{globalPlatformFilter}</span>
      {allProjects.map((p) => (
        <button key={p.id} data-testid={`switch-${p.key}`} onClick={() => setCurrentProject(p)}>
          {p.name}
        </button>
      ))}
      <button data-testid="set-platform-github" onClick={() => setGlobalPlatformFilter("github")}>
        GitHub
      </button>
      <button data-testid="refresh-alpha" onClick={() => void refreshProjects(10)}>
        Refresh Alpha
      </button>
    </div>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
  window.history.replaceState({}, "", "/");
});

describe("ProjectContext", () => {
  it("starts with no selected project and isLoadingProjects=true initially", () => {
    // Slow fetch that never resolves during this test
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    render(<ProjectProvider><Consumer /></ProjectProvider>);
    expect(screen.getByTestId("current").textContent).toBe("none");
    expect(screen.getByTestId("loading").textContent).toBe("true");
  });

  it("loads real projects and sets first as current", async () => {
    vi.stubGlobal("fetch", mockFetchProjects(BACKEND_PROJECTS));
    render(<ProjectProvider><Consumer /></ProjectProvider>);

    await waitFor(() =>
      expect(screen.getByTestId("loading").textContent).toBe("false"),
    );

    expect(screen.getByTestId("current").textContent).toBe("Alpha");
    expect(screen.getByTestId("count").textContent).toBe("2");
  });

  it("clears projects gracefully when API fails", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("network error"))));
    render(<ProjectProvider><Consumer /></ProjectProvider>);

    await waitFor(() =>
      expect(screen.getByTestId("loading").textContent).toBe("false"),
    );

    expect(screen.getByTestId("current").textContent).toBe("none");
    expect(screen.getByTestId("count").textContent).toBe("0");
  });

  it("can switch current project", async () => {
    vi.stubGlobal("fetch", mockFetchProjects(BACKEND_PROJECTS));
    render(<ProjectProvider><Consumer /></ProjectProvider>);

    await waitFor(() =>
      expect(screen.getByTestId("loading").textContent).toBe("false"),
    );

    fireEvent.click(screen.getByTestId("switch-BET"));
    expect(screen.getByTestId("current").textContent).toBe("Beta");
  });

  it("throws if useProject used outside provider", () => {
    // Suppress the expected React error boundary noise
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Consumer />)).toThrow(
      "useProject must be used within a ProjectProvider",
    );
    spy.mockRestore();
  });

  it("keeps no selection when backend returns empty list", async () => {
    vi.stubGlobal("fetch", mockFetchProjects([]));
    render(<ProjectProvider><Consumer /></ProjectProvider>);

    await waitFor(() =>
      expect(screen.getByTestId("loading").textContent).toBe("false"),
    );

    expect(screen.getByTestId("current").textContent).toBe("none");
    expect(screen.getByTestId("count").textContent).toBe("0");
  });

  it("uses the project query parameter when it matches a loaded project key", async () => {
    window.history.replaceState({}, "", "/?project=BET");
    vi.stubGlobal("fetch", mockFetchProjects(BACKEND_PROJECTS));

    render(<ProjectProvider><Consumer /></ProjectProvider>);

    await waitFor(() =>
      expect(screen.getByTestId("loading").textContent).toBe("false"),
    );

    expect(screen.getByTestId("current").textContent).toBe("Beta");
  });

  it("restores the previously selected project from localStorage", async () => {
    window.localStorage.setItem("sprintpulse.currentProjectId", "11");
    vi.stubGlobal("fetch", mockFetchProjects(BACKEND_PROJECTS));

    render(<ProjectProvider><Consumer /></ProjectProvider>);

    await waitFor(() =>
      expect(screen.getByTestId("loading").textContent).toBe("false"),
    );

    expect(screen.getByTestId("current").textContent).toBe("Beta");
  });

  it("restores the platform filter from localStorage", async () => {
    window.localStorage.setItem("sprintpulse.platformFilter", "github");
    vi.stubGlobal("fetch", mockFetchProjects(BACKEND_PROJECTS));

    render(<ProjectProvider><Consumer /></ProjectProvider>);

    await waitFor(() =>
      expect(screen.getByTestId("loading").textContent).toBe("false"),
    );

    expect(screen.getByTestId("platform").textContent).toBe("github");
  });

  it("persists platform filter changes to localStorage", async () => {
    vi.stubGlobal("fetch", mockFetchProjects(BACKEND_PROJECTS));

    render(<ProjectProvider><Consumer /></ProjectProvider>);

    await waitFor(() =>
      expect(screen.getByTestId("loading").textContent).toBe("false"),
    );

    fireEvent.click(screen.getByTestId("set-platform-github"));
    expect(screen.getByTestId("platform").textContent).toBe("github");
    expect(window.localStorage.getItem("sprintpulse.platformFilter")).toBe("github");
  });

  it("falls back to all platform when stored filter is invalid", async () => {
    window.localStorage.setItem("sprintpulse.platformFilter", "asana");
    vi.stubGlobal("fetch", mockFetchProjects(BACKEND_PROJECTS));

    render(<ProjectProvider><Consumer /></ProjectProvider>);

    await waitFor(() =>
      expect(screen.getByTestId("loading").textContent).toBe("false"),
    );

    expect(screen.getByTestId("platform").textContent).toBe("all");
  });

  it("ignores invalid stored project ids and can refresh to a selected project id", async () => {
    window.localStorage.setItem("sprintpulse.currentProjectId", "not-a-number");
    vi.stubGlobal("fetch", mockFetchProjects(BACKEND_PROJECTS));

    render(<ProjectProvider><Consumer /></ProjectProvider>);

    await waitFor(() =>
      expect(screen.getByTestId("loading").textContent).toBe("false"),
    );

    expect(screen.getByTestId("current").textContent).toBe("Alpha");

    fireEvent.click(screen.getByTestId("switch-BET"));
    expect(screen.getByTestId("current").textContent).toBe("Beta");

    fireEvent.click(screen.getByTestId("refresh-alpha"));
    await waitFor(() =>
      expect(screen.getByTestId("current").textContent).toBe("Alpha"),
    );
  });

  it("handles refresh completion after unmount", async () => {
    let resolveFetch: (value: unknown) => void = () => {};
    vi.stubGlobal("fetch", vi.fn(() => new Promise((resolve) => {
      resolveFetch = resolve;
    })));

    const { unmount } = render(<ProjectProvider><Consumer /></ProjectProvider>);
    unmount();

    await act(async () => {
      resolveFetch({
        ok: true,
        status: 200,
        statusText: "OK",
        headers: { get: () => null },
        json: () => Promise.resolve({ items: BACKEND_PROJECTS, total: 2, page: 1, page_size: 100 }),
      });
    });
  });
});

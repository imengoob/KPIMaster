import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DashboardLayout from "@/components/DashboardLayout";

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({
    currentProject: { id: 1, name: "Phoenix Launch", key: "PHX", color: "#0891b2", repositoryUrl: null },
    setCurrentProject: vi.fn(),
    allProjects: [{ id: 1, name: "Phoenix Launch", key: "PHX", color: "#0891b2", repositoryUrl: null }],
    isLoadingProjects: false,
    refreshProjects: vi.fn().mockResolvedValue([]),
    globalDateRange: undefined,
    setGlobalDateRange: vi.fn(),
    globalPlatformFilter: "all",
    setGlobalPlatformFilter: vi.fn(),
  }),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    logout: vi.fn(),
    user: {
      id: 1,
      username: "horizon_admin",
      email: "admin@example.com",
      role: "client_admin",
      company_name: "Horizon",
    },
  }),
  isDeveloperUser: () => false,
}));

vi.mock("@/services/api/trello", () => ({
  trelloApi: {
    syncProject: vi.fn().mockResolvedValue(undefined),
  },
}));

function renderLayout() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/dashboard"]}>
        <DashboardLayout>
          <div>Dashboard body</div>
        </DashboardLayout>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DashboardLayout", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("exposes a mobile navigation drawer control", () => {
    renderLayout();

    fireEvent.click(screen.getByRole("button", { name: /open navigation/i }));

    expect(screen.getByRole("button", { name: /close navigation/i })).toBeInTheDocument();
    expect(screen.getByText("Dashboard body")).toBeInTheDocument();
  });
});

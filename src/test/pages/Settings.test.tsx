import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Settings from "@/pages/Settings";

const mocks = vi.hoisted(() => ({
  refreshProjects: vi.fn(),
  getSettings: vi.fn(),
  saveSettings: vi.fn(),
  listAvailableBoards: vi.fn(),
  importBoards: vi.fn(),
  getMine: vi.fn(),
  updateMine: vi.fn(),
}));

vi.mock("@/components/DashboardLayout", () => ({
  default: ({ children }: { children: React.ReactNode }) => <div data-testid="layout">{children}</div>,
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: 1,
      username: "admin",
      email: "admin@sprintpulse.test",
      role: "company_admin",
      company_id: 10,
      developer_id: null,
      is_active: true,
    },
  }),
  isDeveloperUser: () => false,
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({
    refreshProjects: mocks.refreshProjects,
    globalPlatformFilter: "all",
    setGlobalPlatformFilter: vi.fn(),
  }),
}));

vi.mock("@/services/api/companies", () => ({
  companyApi: {
    getMine: mocks.getMine,
    updateMine: mocks.updateMine,
  },
}));

vi.mock("@/services/api/trello", () => ({
  trelloApi: {
    getSettings: mocks.getSettings,
    saveSettings: mocks.saveSettings,
    listAvailableBoards: mocks.listAvailableBoards,
    importBoards: mocks.importBoards,
  },
}));

function renderSettings() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <Settings />
    </QueryClientProvider>,
  );
}

async function openTrelloSettings() {
  renderSettings();
  const tab = await screen.findByRole("tab", { name: /trello integration/i });
  fireEvent.pointerDown(tab, { button: 0, ctrlKey: false });
  fireEvent.click(tab);
  fireEvent.keyDown(tab, { key: "Enter" });
  await screen.findByRole("heading", { name: /connect a real trello board/i });
}

describe("Settings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getSettings.mockResolvedValue({
      has_credentials: false,
      api_key: "",
      api_token: "",
      selected_board_ids: [],
    });
    mocks.getMine.mockResolvedValue({
      id: 10,
      name: "Norma Tunisie",
      slug: "norma-tunisie",
      tenant_type: "client",
      description: "",
      contact_email: "admin@sprintpulse.test",
      is_active: true,
    });
    mocks.refreshProjects.mockResolvedValue([]);
  });

  it("loads available boards from Trello settings", async () => {
    mocks.listAvailableBoards.mockResolvedValue([
      {
        id: "board_1",
        name: "Platform Delivery",
        description: "Main delivery board",
        short_url: "https://trello.com/b/board_1",
        is_closed: false,
        organization_id: null,
      },
      {
        id: "board_2",
        name: "Old Board",
        description: null,
        short_url: null,
        is_closed: true,
        organization_id: null,
      },
    ]);

    await openTrelloSettings();

    fireEvent.click(await screen.findByRole("button", { name: /load available boards/i }));

    expect(await screen.findByText("Platform Delivery")).toBeInTheDocument();
    expect(screen.getByText("Old Board")).toBeInTheDocument();
    expect(mocks.listAvailableBoards).toHaveBeenCalledWith({
      apiKey: undefined,
      apiToken: undefined,
    });
  });

  it("does not block ATTA-prefixed Trello tokens before loading boards", async () => {
    const attaToken = "ATTA" + "d".repeat(60);
    mocks.getSettings.mockResolvedValue({
      has_credentials: true,
      api_key: "saved-key",
      api_token: attaToken,
      selected_board_ids: [],
    });
    mocks.listAvailableBoards.mockResolvedValue([
      {
        id: "board_atta",
        name: "ATTA Token Board",
        description: null,
        short_url: null,
        is_closed: false,
        organization_id: null,
      },
    ]);

    await openTrelloSettings();

    await screen.findByDisplayValue(attaToken);
    fireEvent.click(screen.getByRole("button", { name: /load available boards/i }));

    await waitFor(() => {
      expect(mocks.listAvailableBoards).toHaveBeenCalledWith({
        apiKey: "saved-key",
        apiToken: attaToken,
      });
    });
    expect(await screen.findByText("ATTA Token Board")).toBeInTheDocument();
  });

  it("imports selected boards and refreshes the project switcher selection", async () => {
    mocks.listAvailableBoards.mockResolvedValue([
      {
        id: "board_1",
        name: "Platform Delivery",
        description: null,
        short_url: "https://trello.com/b/board_1",
        is_closed: false,
        organization_id: null,
      },
      {
        id: "board_2",
        name: "Phoenix Mobile",
        description: null,
        short_url: "https://trello.com/b/board_2",
        is_closed: false,
        organization_id: null,
      },
    ]);
    mocks.importBoards.mockResolvedValue([
      {
        project_id: 42,
        project_key: "PLAT",
        board_id: 10,
        board_name: "Platform Delivery",
        trello_board_id: "board_1",
        short_url: "https://trello.com/b/board_1",
      },
    ]);

    await openTrelloSettings();

    fireEvent.click(await screen.findByRole("button", { name: /load available boards/i }));
    await screen.findByText("Phoenix Mobile");

    fireEvent.click(screen.getByRole("button", { name: /^clear$/i }));
    fireEvent.click(screen.getByText("Platform Delivery").closest("label")!);
    fireEvent.click(screen.getByRole("button", { name: /import selected boards/i }));

    await waitFor(() => {
      expect(mocks.importBoards).toHaveBeenCalledWith({
        apiKey: undefined,
        apiToken: undefined,
        boardIds: ["board_1"],
      });
    });
    await waitFor(() => expect(mocks.refreshProjects).toHaveBeenCalledWith(42));
    expect(await screen.findByText("Imported projects")).toBeInTheDocument();
  });

  it("imports a saved board selection without reloading the board list first", async () => {
    mocks.getSettings.mockResolvedValue({
      has_credentials: true,
      api_key: "saved-key",
      api_token: "b".repeat(64),
      selected_board_ids: ["board_saved"],
    });
    mocks.importBoards.mockResolvedValue([
      {
        project_id: 7,
        project_key: "SAVED",
        board_id: 70,
        board_name: "Saved Board",
        trello_board_id: "board_saved",
        short_url: null,
      },
    ]);

    await openTrelloSettings();

    await screen.findByText(/Settings loaded from database/i);
    fireEvent.click(screen.getByRole("button", { name: /import selected boards/i }));

    await waitFor(() => {
      expect(mocks.importBoards).toHaveBeenCalledWith({
        apiKey: "saved-key",
        apiToken: "b".repeat(64),
        boardIds: ["board_saved"],
      });
    });
    await waitFor(() => expect(mocks.refreshProjects).toHaveBeenCalledWith(7));
  });
});

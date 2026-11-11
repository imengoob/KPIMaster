import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

import type { BackendActionItem, BackendActionItemDetail } from "@/services/api/types";

const queryMock = vi.hoisted(() => ({
  listState: {
    data: [] as BackendActionItem[],
    isLoading: false,
    isError: false,
  },
  detailState: {
    data: undefined as BackendActionItemDetail | undefined,
    isLoading: false,
    isError: false,
  },
  generateMutate: vi.fn(),
  transitionMutate: vi.fn(),
}));

vi.mock("@/components/DashboardLayout", () => ({
  default: ({ children }: { children: React.ReactNode }) => <div data-testid="layout">{children}</div>,
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({
    currentProject: {
      id: 1,
      name: "Norma Base Project",
      key: "NOR",
      color: "#0f766e",
      repositoryUrl: null,
    },
  }),
}));

vi.mock("@/components/ui/use-toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: ({ queryKey }: { queryKey: unknown[] }) => (
    queryKey[1] === "detail" ? queryMock.detailState : queryMock.listState
  ),
  useQueryClient: () => ({
    invalidateQueries: vi.fn(),
  }),
  useMutation: (options: { mutationFn: unknown; onSuccess?: (data: unknown) => void }) => {
    const isTransition = options.mutationFn instanceof Function && options.mutationFn.toString().includes("transition");
    return {
      mutate: (variables?: unknown) => {
        if (isTransition) {
          queryMock.transitionMutate(variables);
          options.onSuccess?.({ ...openAction, status: "resolved" });
          return;
        }
        queryMock.generateMutate(variables);
        options.onSuccess?.({ generated: 1, refreshed: 1, total_open: 2 });
      },
      isPending: false,
      isError: false,
    };
  },
}));

const openAction: BackendActionItemDetail = {
  id: 42,
  project_id: 1,
  source_type: "blocker",
  source_id: "blocker-42",
  source_url: null,
  title: "Resolve checkout API blocker",
  description: "The checkout API ticket has been stalled long enough to affect the sprint commitment.",
  recommended_action: "Ask the owner for a recovery plan and escalation note.",
  priority: "critical",
  owner_user_id: null,
  owner_role: "delivery_lead",
  status: "awaiting_approval",
  approval_required: true,
  due_at: "2024-01-01T10:00:00Z",
  resolved_at: null,
  metadata_json: {},
  created_at: "2024-01-01T08:00:00Z",
  updated_at: "2024-01-01T09:00:00Z",
  events: [
    {
      id: 1,
      action_item_id: 42,
      actor_user_id: null,
      event_type: "created",
      previous_status: null,
      next_status: "open",
      note: "Detected by blocker scan.",
      payload_json: {},
      created_at: "2024-01-01T08:00:00Z",
    },
  ],
};

const resolvedAction: BackendActionItem = {
  ...openAction,
  id: 43,
  source_type: "ticket_quality",
  source_id: "ticket-43",
  title: "Improve ticket acceptance criteria",
  recommended_action: "Add testable acceptance criteria before sprint review.",
  priority: "medium",
  status: "resolved",
  due_at: null,
  resolved_at: "2024-01-02T10:00:00Z",
};

describe("Actions", () => {
  let Actions: React.ComponentType;

  beforeEach(async () => {
    queryMock.listState = {
      data: [openAction, resolvedAction],
      isLoading: false,
      isError: false,
    };
    queryMock.detailState = {
      data: openAction,
      isLoading: false,
      isError: false,
    };
    queryMock.generateMutate.mockClear();
    queryMock.transitionMutate.mockClear();

    const mod = await import("@/pages/Actions");
    Actions = mod.default;
  });

  it("renders the project action queue with summary stats", () => {
    render(<Actions />);

    expect(screen.getByText("Action Center - Norma Base Project")).toBeInTheDocument();
    expect(screen.getByText("Resolve checkout API blocker")).toBeInTheDocument();
    expect(screen.getByText("Improve ticket acceptance criteria")).toBeInTheDocument();
    expect(screen.getAllByText("Critical").length).toBeGreaterThan(0);
    expect(screen.getByText("Awaiting Approval")).toBeInTheDocument();
  });

  it("switches queue views and refreshes generated actions", () => {
    render(<Actions />);

    fireEvent.click(screen.getByRole("button", { name: /^critical$/i }));
    expect(screen.getByText("Resolve checkout API blocker")).toBeInTheDocument();
    expect(screen.queryByText("Improve ticket acceptance criteria")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^resolved$/i }));
    expect(screen.getByText("Improve ticket acceptance criteria")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^mine$/i }));
    expect(screen.getByText("Resolve checkout API blocker")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^generate$/i }));
    expect(queryMock.generateMutate).toHaveBeenCalled();
  });

  it("shows loading and error states", () => {
    queryMock.listState = { data: [], isLoading: true, isError: false };
    const { rerender } = render(<Actions />);
    expect(screen.getByTestId("loading-spinner")).toBeInTheDocument();

    queryMock.listState = { data: [], isLoading: false, isError: true };
    rerender(<Actions />);
    expect(screen.getByTestId("error-state")).toBeInTheDocument();
  });

  it("opens action details and dispatches a transition", () => {
    render(<Actions />);

    fireEvent.click(screen.getAllByRole("button", { name: /open/i })[0]);

    expect(screen.getAllByText("Resolve checkout API blocker").length).toBeGreaterThan(0);
    expect(screen.getByText(/checkout API ticket has been stalled/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /resolve/i }));
    expect(queryMock.transitionMutate).toHaveBeenCalledWith({
      id: 42,
      transition: "resolve",
      note: undefined,
    });
  });
});

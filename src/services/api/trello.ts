import { apiFetch } from "./config";
import type {
  BackendAvailableTrelloBoard,
  BackendBoardSummary,
  BackendImportedTrelloProject,
  BackendTrelloSettings,
} from "./types";

export interface ImportTrelloBoardsInput {
  apiKey?: string;
  apiToken?: string;
  boardIds?: string[];
}

export interface SaveTrelloSettingsInput {
  apiKey?: string;
  apiToken?: string;
  selectedBoardIds: string[];
}

export const trelloApi = {
  getSettings: () =>
    apiFetch<BackendTrelloSettings>("/trello/settings"),

  saveSettings: (input: SaveTrelloSettingsInput) =>
    apiFetch<BackendTrelloSettings>("/trello/settings", {
      method: "POST",
      body: JSON.stringify({
        api_key: input.apiKey || null,
        api_token: input.apiToken || null,
        selected_board_ids: input.selectedBoardIds,
      }),
    }),

  listAvailableBoards: (input: ImportTrelloBoardsInput) =>
    apiFetch<BackendAvailableTrelloBoard[]>("/trello/available-boards", {
      method: "POST",
      body: JSON.stringify({
        api_key: input.apiKey || null,
        api_token: input.apiToken || null,
        board_ids: input.boardIds ?? [],
      }),
    }),

  importBoards: (input: ImportTrelloBoardsInput) =>
    apiFetch<BackendImportedTrelloProject[]>("/trello/import-boards", {
      method: "POST",
      body: JSON.stringify({
        api_key: input.apiKey || null,
        api_token: input.apiToken || null,
        board_ids: input.boardIds ?? [],
      }),
    }),

  /** Pull fresh data from Trello for all boards linked to a project. */
  syncProject: (projectId: number, full = false) =>
    apiFetch<{ project_id: number; boards_synced: number; boards_total: number; results: unknown[] }>(
      `/trello/projects/${projectId}/sync?full=${full}`,
      { method: "POST" },
    ),

  /** Per-list card counts + KPIs derived from actual board list names. */
  getProjectBoardSummary: (projectId: number, startDate?: string | null, endDate?: string | null) => {
    const params = new URLSearchParams();
    if (startDate) params.set("start_date", startDate);
    if (endDate) params.set("end_date", endDate);
    const suffix = params.toString();
    return apiFetch<BackendBoardSummary>(
      `/trello/projects/${projectId}/board-summary${suffix ? `?${suffix}` : ""}`,
    );
  },

  /** Re-apply classification rules to existing lists (no Trello API call). */
  reclassifyBoardLists: (boardId: number) =>
    apiFetch<{ board_id: number; lists_updated: number; lists: unknown[] }>(
      `/trello/boards/${boardId}/reclassify-lists`,
      { method: "POST" },
    ),
};

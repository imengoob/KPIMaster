export type PlatformFilter = "all" | "trello" | "github" | "jira" | "microsoft";

export const PLATFORM_LABELS: Record<PlatformFilter, string> = {
  all: "All Platforms",
  trello: "Trello",
  github: "GitHub",
  jira: "Jira",
  microsoft: "Planner",
};

export const PLATFORM_OPTIONS: PlatformFilter[] = [
  "all",
  "trello",
  "github",
  "jira",
  "microsoft",
];

export function getProviderParam(platform: PlatformFilter) {
  return platform === "all" ? undefined : platform;
}

export function isTrelloCompatiblePlatform(platform: PlatformFilter) {
  return platform === "all" || platform === "trello";
}

const fallbackBaseUrl = "http://localhost:8000";

declare const process: {
  env: Record<string, string | undefined>;
};

export function getApiBaseUrl(): string {
  const fromExpoPublic = process.env.EXPO_PUBLIC_API_BASE_URL;
  return (fromExpoPublic || fallbackBaseUrl).replace(/\/$/, "");
}

export function getApiV1Url(): string {
  return `${getApiBaseUrl()}/api/v1`;
}

export function getWebSocketBaseUrl(): string {
  return getApiBaseUrl().replace(/^http/, "ws");
}

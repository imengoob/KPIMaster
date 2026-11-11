// Base API configuration — all requests route to /api/v1/...
export const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) || "http://localhost:8000";

/** Prepend this to every endpoint path */
export const API_V1 = `${API_BASE_URL}/api/v1`;
export const AUTH_TOKEN_STORAGE_KEY = "kpimaster.authToken";

export const defaultHeaders: Record<string, string> = {
  "Content-Type": "application/json",
};

export class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public body?: unknown,
  ) {
    super(`API Error ${status}: ${statusText}`);
    this.name = "ApiError";
  }
}

export class ApiNetworkError extends Error {
  constructor(public url: string, cause?: unknown) {
    super(
      `Could not reach the KPIMaster API at ${url}. Check that the backend is running, CORS is enabled for this frontend origin, and VITE_API_BASE_URL points to the FastAPI server.`,
    );
    this.name = "ApiNetworkError";
    this.cause = cause;
  }
}

/**
 * Fired whenever any API call receives a 401.
 * AuthContext subscribes to this to force-logout without creating a circular
 * dependency between apiFetch and the React context.
 */
export const authBus = new EventTarget();
export const AUTH_EXPIRED_EVENT = "auth:expired";

/**
 * Thin fetch wrapper. `endpoint` must start with `/`.
 * Automatically prefixes with API_V1 and attaches the Bearer token from
 * localStorage. On 401, emits an "auth:expired" event so the AuthContext
 * can clear state and redirect to /login without a page reload.
 */
export async function apiFetch<T>(
  endpoint: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${API_V1}${endpoint}`;
  const token =
    typeof window !== "undefined"
      ? window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)
      : null;

  const authHeader: Record<string, string> = token
    ? { Authorization: `Bearer ${token}` }
    : {};

  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      headers: { ...defaultHeaders, ...authHeader, ...(options.headers as Record<string, string> | undefined) },
    });
  } catch (error) {
    throw new ApiNetworkError(url, error);
  }

  if (response.status === 401) {
    // Token is missing, invalid, or expired — tell AuthContext to log out.
    authBus.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, response.statusText, body);
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, response.statusText, body);
  }

  // 204 No Content — return undefined without trying to parse JSON
  if (response.status === 204 || response.headers.get("content-length") === "0") {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

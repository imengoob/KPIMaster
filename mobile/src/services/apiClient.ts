import { getApiV1Url } from "../config/env";
import { appStorage, TOKEN_STORAGE_KEY } from "./storage";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly statusText: string,
    public readonly body: unknown
  ) {
    super(`API ${status}: ${statusText}`);
    this.name = "ApiError";
  }
}

export class ApiNetworkError extends Error {
  constructor(public readonly url: string, cause: unknown) {
    super(`Could not reach KPIMaster API at ${url}`);
    this.name = "ApiNetworkError";
    this.cause = cause;
  }
}

export type Fetcher = typeof fetch;

export interface ApiClientOptions {
  baseUrl?: string;
  tokenProvider?: () => Promise<string | null>;
  onUnauthorized?: () => Promise<void> | void;
  fetcher?: Fetcher;
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly tokenProvider: () => Promise<string | null>;
  private readonly onUnauthorized?: () => Promise<void> | void;
  private readonly fetcher: Fetcher;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? getApiV1Url();
    this.tokenProvider = options.tokenProvider ?? (() => appStorage.getItem(TOKEN_STORAGE_KEY));
    this.onUnauthorized = options.onUnauthorized;
    this.fetcher = options.fetcher ?? fetch;
  }

  async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const token = await this.tokenProvider();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string> | undefined)
    };
    if (token) headers.Authorization = `Bearer ${token}`;

    let response: Response;
    try {
      response = await this.fetcher(url, { ...options, headers });
    } catch (error) {
      throw new ApiNetworkError(url, error);
    }

    if (response.status === 401) {
      await this.onUnauthorized?.();
      const body = await response.json().catch(() => null);
      throw new ApiError(response.status, response.statusText, body);
    }

    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new ApiError(response.status, response.statusText, body);
    }

    if (response.status === 204 || response.headers.get("content-length") === "0") {
      return undefined as T;
    }

    return response.json() as Promise<T>;
  }
}

export const apiClient = new ApiClient({
  onUnauthorized: () => appStorage.removeItem(TOKEN_STORAGE_KEY)
});

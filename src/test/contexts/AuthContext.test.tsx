import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  AuthProvider,
  getApiErrorMessage,
  getDefaultHomePath,
  isCompanyUser,
  isDeveloperUser,
  useAuth,
} from "@/contexts/AuthContext";
import { authApi } from "@/services/api/auth";
import { AUTH_EXPIRED_EVENT, ApiError, authBus } from "@/services/api/config";

vi.mock("@/services/api/auth", () => ({
  authApi: {
    login: vi.fn(),
    me: vi.fn(),
    register: vi.fn(),
  },
}));

function renderWithProvider(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(createElement(QueryClientProvider, { client }, ui));
}

function Consumer() {
  const { user, isAuthenticated, isAuthLoading, login, register, logout } = useAuth();
  return (
    <div>
      <span data-testid="loading">{String(isAuthLoading)}</span>
      <span data-testid="authenticated">{String(isAuthenticated)}</span>
      <span data-testid="user">{user?.username ?? "none"}</span>
      <button data-testid="login" onClick={() => login("alice", "secret")}>login</button>
      <button
        data-testid="register"
        onClick={() => register({ username: "bob", email: "bob@example.com", password: "secret" })}
      >
        register
      </button>
      <button data-testid="logout" onClick={logout}>logout</button>
    </div>
  );
}

describe("AuthContext", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("starts unauthenticated when no stored token exists", async () => {
    renderWithProvider(<AuthProvider><Consumer /></AuthProvider>);

    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
    expect(screen.getByTestId("authenticated")).toHaveTextContent("false");
    expect(screen.getByTestId("user")).toHaveTextContent("none");
  });

  it("restores the current user from a stored token", async () => {
    window.localStorage.setItem("kpimaster.authToken", "jwt");
    vi.mocked(authApi.me).mockResolvedValue({
      id: 1,
      username: "alice",
      email: "alice@example.com",
      role: "developer",
      company_id: null,
      developer_id: 5,
      is_active: true,
    });

    renderWithProvider(<AuthProvider><Consumer /></AuthProvider>);

    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("alice"));
    expect(screen.getByTestId("authenticated")).toHaveTextContent("true");
  });

  it("clears an invalid stored token when me fails", async () => {
    window.localStorage.setItem("kpimaster.authToken", "bad-jwt");
    vi.mocked(authApi.me).mockRejectedValue(new Error("expired"));

    renderWithProvider(<AuthProvider><Consumer /></AuthProvider>);

    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
    expect(window.localStorage.getItem("kpimaster.authToken")).toBeNull();
    expect(screen.getByTestId("user")).toHaveTextContent("none");
  });

  it("logs in, stores the token, and loads the user", async () => {
    vi.mocked(authApi.login).mockResolvedValue({ access_token: "fresh-jwt", token_type: "bearer" });
    vi.mocked(authApi.me).mockResolvedValue({
      id: 2,
      username: "alice",
      email: "alice@example.com",
      role: "company_admin",
      company_id: 10,
      developer_id: null,
      is_active: true,
    });

    renderWithProvider(<AuthProvider><Consumer /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));

    await act(async () => {
      fireEvent.click(screen.getByTestId("login"));
    });

    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("alice"));
    expect(window.localStorage.getItem("kpimaster.authToken")).toBe("fresh-jwt");
    expect(vi.mocked(authApi.login)).toHaveBeenCalledWith({ username: "alice", password: "secret" });
  });

  it("registers then logs the user in", async () => {
    vi.mocked(authApi.register).mockResolvedValue({
      id: 3,
      username: "bob",
      email: "bob@example.com",
      role: "company_admin",
      company_id: 11,
      developer_id: null,
      is_active: true,
    });
    vi.mocked(authApi.login).mockResolvedValue({ access_token: "register-jwt", token_type: "bearer" });
    vi.mocked(authApi.me).mockResolvedValue({
      id: 3,
      username: "bob",
      email: "bob@example.com",
      role: "company_admin",
      company_id: 11,
      developer_id: null,
      is_active: true,
    });

    renderWithProvider(<AuthProvider><Consumer /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));

    await act(async () => {
      fireEvent.click(screen.getByTestId("register"));
    });

    expect(vi.mocked(authApi.register)).toHaveBeenCalledWith({
      username: "bob",
      email: "bob@example.com",
      password: "secret",
    });
    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("bob"));
  });

  it("logs out on explicit logout and on auth-expired events", async () => {
    window.localStorage.setItem("kpimaster.authToken", "jwt");
    vi.mocked(authApi.me).mockResolvedValue({
      id: 1,
      username: "alice",
      email: "alice@example.com",
      role: "developer",
      company_id: null,
      developer_id: 5,
      is_active: true,
    });

    renderWithProvider(<AuthProvider><Consumer /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("alice"));

    fireEvent.click(screen.getByTestId("logout"));
    expect(screen.getByTestId("user")).toHaveTextContent("none");
    expect(window.localStorage.getItem("kpimaster.authToken")).toBeNull();

    window.localStorage.setItem("kpimaster.authToken", "jwt");
    await act(async () => {
      authBus.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    });
    expect(window.localStorage.getItem("kpimaster.authToken")).toBeNull();
  });

  it("throws when useAuth is used outside the provider", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Consumer />)).toThrow("useAuth must be used within an AuthProvider");
    spy.mockRestore();
  });
});

describe("AuthContext helpers", () => {
  it("classifies roles and default home paths", () => {
    expect(isDeveloperUser({ role: "developer" } as any)).toBe(true);
    expect(isCompanyUser({ role: "super_admin" } as any)).toBe(true);
    expect(getDefaultHomePath({ role: "developer" } as any)).toBe("/developers");
    expect(getDefaultHomePath({ role: "esn_admin" } as any)).toBe("/developers");
    expect(getDefaultHomePath({ role: "company_admin" } as any)).toBe("/dashboard");
  });

  it("formats API and runtime errors", () => {
    expect(getApiErrorMessage(new ApiError(400, "Bad Request", { detail: "Invalid token" }))).toBe("Invalid token");
    expect(getApiErrorMessage(new ApiError(422, "Validation failed", { detail: [{ msg: "Username required" }] }))).toBe("Username required");
    expect(getApiErrorMessage(new ApiError(422, "Validation failed", { detail: [{ msg: null }, "plain"] }))).toBe("Validation error, Validation error");
    expect(getApiErrorMessage(new ApiError(403, "", { detail: 123 }))).toBe("Authentication failed.");
    expect(getApiErrorMessage(new Error("Network down"))).toBe("Network down");
    expect(getApiErrorMessage("oops")).toBe("Authentication failed.");
  });
});

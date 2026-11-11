import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const authMock = vi.hoisted(() => ({
  state: {
    isAuthenticated: false,
    isAuthLoading: false,
    user: null,
    login: vi.fn(),
    register: vi.fn(),
  },
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => authMock.state,
  getApiErrorMessage: (err: unknown) => err instanceof Error ? err.message : "Something went wrong.",
  getDefaultHomePath: () => "/dashboard",
}));

import Login from "@/pages/Login";
import Register from "@/pages/Register";

function renderAuthRoute(element: React.ReactElement, initialEntry: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path={initialEntry} element={element} />
        <Route path="/" element={<div>Home</div>} />
        <Route path="/dashboard" element={<div>Dashboard</div>} />
        <Route path="/login" element={<div>Login link target</div>} />
        <Route path="/register" element={<div>Register link target</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Login", () => {
  beforeEach(() => {
    authMock.state = {
      isAuthenticated: false,
      isAuthLoading: false,
      user: null,
      login: vi.fn().mockResolvedValue(undefined),
      register: vi.fn(),
    };
  });

  it("submits credentials and routes to the app shell", async () => {
    renderAuthRoute(<Login />, "/login");

    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: "norma_admin" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "Password123!" } });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(authMock.state.login).toHaveBeenCalledWith("norma_admin", "Password123!");
      expect(screen.getByText("Home")).toBeInTheDocument();
    });
  });

  it("shows API errors without losing the login form", async () => {
    authMock.state.login = vi.fn().mockRejectedValue(new Error("Invalid credentials"));
    renderAuthRoute(<Login />, "/login");

    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: "bad-user" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText("Invalid credentials")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });
});

describe("Register", () => {
  beforeEach(() => {
    authMock.state = {
      isAuthenticated: false,
      isAuthLoading: false,
      user: null,
      login: vi.fn(),
      register: vi.fn().mockResolvedValue(undefined),
    };
  });

  it("blocks mismatched passwords before calling the API", () => {
    renderAuthRoute(<Register />, "/register");

    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: "new_admin" } });
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: "new@example.com" } });
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "Password123!" } });
    fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: "Different123!" } });
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));

    expect(screen.getByText("Passwords do not match.")).toBeInTheDocument();
    expect(authMock.state.register).not.toHaveBeenCalled();
  });

  it("creates a client company account with the selected form values", async () => {
    renderAuthRoute(<Register />, "/register");

    fireEvent.change(screen.getByLabelText(/company name/i), { target: { value: "Norma Tunisie" } });
    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: "norma_admin" } });
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: "norma@example.com" } });
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "Password123!" } });
    fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: "Password123!" } });
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => {
      expect(authMock.state.register).toHaveBeenCalledWith({
        username: "norma_admin",
        email: "norma@example.com",
        password: "Password123!",
        account_type: "company_admin",
        company_name: "Norma Tunisie",
        company_slug: undefined,
        company_type: "client",
      });
      expect(screen.getByText("Home")).toBeInTheDocument();
    });
  });
});

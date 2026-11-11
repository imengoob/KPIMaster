import { apiFetch } from "./config";
import type { BackendAuthToken, BackendAuthUser } from "./types";

export interface LoginInput {
  username: string;
  password: string;
}

export interface RegisterInput {
  username: string;
  email: string;
  password: string;
  account_type?: "company_admin" | "client_admin" | "esn_admin" | "developer";
  company_name?: string;
  company_slug?: string;
  company_type?: "client" | "vendor";
}

export const authApi = {
  login: (input: LoginInput) =>
    apiFetch<BackendAuthToken>("/auth/login", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  register: (input: RegisterInput) =>
    apiFetch<BackendAuthUser>("/auth/register", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  me: () => apiFetch<BackendAuthUser>("/auth/me"),
};

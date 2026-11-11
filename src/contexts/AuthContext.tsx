import { createContext, ReactNode, useContext, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { authApi, type RegisterInput } from "@/services/api/auth";
import { AUTH_EXPIRED_EVENT, AUTH_TOKEN_STORAGE_KEY, ApiError, authBus } from "@/services/api/config";
import type { BackendAuthUser } from "@/services/api/types";

interface AuthContextType {
  user: BackendAuthUser | null;
  isAuthenticated: boolean;
  isAuthLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (input: RegisterInput) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<BackendAuthUser | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(true);
  // Keep a stable ref to logout so the event listener doesn't go stale.
  const logoutRef = useRef<() => void>(() => {});

  const logout = () => {
    window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
    setUser(null);
    // Clear every cached query so the next user can't see stale data.
    queryClient.clear();
  };

  // Keep the ref in sync.
  logoutRef.current = logout;

  // On mount: restore session from stored token.
  useEffect(() => {
    let cancelled = false;
    const token = window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
    if (!token) {
      setIsAuthLoading(false);
      return;
    }

    authApi
      .me()
      .then((me) => {
        if (!cancelled) setUser(me);
      })
      .catch(() => {
        // Token is invalid or expired — clear it silently.
        window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
        if (!cancelled) setUser(null);
      })
      .finally(() => {
        if (!cancelled) setIsAuthLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // Listen for any API call that returns 401 and force-logout.
  useEffect(() => {
    const handler = () => logoutRef.current();
    authBus.addEventListener(AUTH_EXPIRED_EVENT, handler);
    return () => authBus.removeEventListener(AUTH_EXPIRED_EVENT, handler);
  }, []);

  const login = async (username: string, password: string) => {
    const token = await authApi.login({ username, password });
    window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token.access_token);
    const me = await authApi.me();
    setUser(me);
  };

  const register = async (input: RegisterInput) => {
    await authApi.register(input);
    await login(input.username, input.password);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: Boolean(user),
        isAuthLoading,
        login,
        register,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
};

export function isDeveloperUser(user: BackendAuthUser | null): boolean {
  return user?.role === "developer";
}

export function isCompanyUser(user: BackendAuthUser | null): boolean {
  return user?.role === "company_admin"
    || user?.role === "company_manager"
    || user?.role === "client_admin"
    || user?.role === "client_exec"
    || user?.role === "client_pm"
    || user?.role === "esn_admin"
    || user?.role === "esn_delivery_manager"
    || user?.role === "auditor_readonly"
    || user?.role === "super_admin";
}

export function getDefaultHomePath(user: BackendAuthUser | null): string {
  if (isDeveloperUser(user)) return "/developers";
  if (user?.role === "esn_admin" || user?.role === "esn_delivery_manager") return "/developers";
  return "/dashboard";
}

export function getApiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (typeof error.body === "object" && error.body !== null && "detail" in error.body) {
      const detail = (error.body as { detail?: unknown }).detail;
      if (Array.isArray(detail)) {
        return detail.map((d: unknown) => {
          if (typeof d === "object" && d !== null && "msg" in d) {
            return String((d as { msg?: unknown }).msg ?? "Validation error");
          }
          return "Validation error";
        }).join(", ");
      }
      if (typeof detail === "string") {
        return detail;
      }
    }
    return error.statusText || "Authentication failed.";
  }
  
  if (error instanceof Error) {
     return error.message;
  }
  
  return "Authentication failed.";
}

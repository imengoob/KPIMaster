import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { AuthUser } from "../domain/types";
import { kpiApi } from "../services/api";
import { appStorage, TOKEN_STORAGE_KEY } from "../services/storage";

interface AuthContextValue {
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  isRestoring: boolean;
  error: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Authentication failed. Check your credentials and API URL.";
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isRestoring, setIsRestoring] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const logout = useCallback(async () => {
    await appStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function restore() {
      try {
        const stored = await appStorage.getItem(TOKEN_STORAGE_KEY);
        if (!stored) return;
        setToken(stored);
        const me = await kpiApi.auth.me();
        if (!cancelled) setUser(me);
      } catch {
        await appStorage.removeItem(TOKEN_STORAGE_KEY);
        if (!cancelled) {
          setToken(null);
          setUser(null);
        }
      } finally {
        if (!cancelled) setIsRestoring(false);
      }
    }

    restore();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    setError(null);
    try {
      const auth = await kpiApi.auth.login(username, password);
      await appStorage.setItem(TOKEN_STORAGE_KEY, auth.access_token);
      setToken(auth.access_token);
      const me = await kpiApi.auth.me();
      setUser(me);
    } catch (err) {
      setError(getErrorMessage(err));
      throw err;
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      token,
      isAuthenticated: Boolean(user),
      isRestoring,
      error,
      login,
      logout,
      clearError: () => setError(null)
    }),
    [error, isRestoring, login, logout, token, user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

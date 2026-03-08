import { createContext, useContext, useState, useCallback } from "react";
import type { ReactNode } from "react";
import { loginStep1Api, verifyTotpApi } from "../api/authApi";
import type { LoginStep1Result } from "../api/authApi";

interface AuthState {
  token: string | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<LoginStep1Result>;
  verifyTotp: (tempToken: string, code: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(
    () => localStorage.getItem("auth_token")
  );

  const login = useCallback(
    async (username: string, password: string): Promise<LoginStep1Result> => {
      return loginStep1Api(username, password);
    },
    []
  );

  const verifyTotp = useCallback(
    async (tempToken: string, code: string): Promise<void> => {
      const t = await verifyTotpApi(tempToken, code);
      localStorage.setItem("auth_token", t);
      setToken(t);
    },
    []
  );

  const logout = useCallback(() => {
    localStorage.removeItem("auth_token");
    setToken(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{ token, isAuthenticated: !!token, login, verifyTotp, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

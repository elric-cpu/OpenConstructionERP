import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import * as authApi from "../api/client";

type LoginInput = Parameters<typeof authApi.login>[0];
type AuthState = {
  authenticated: boolean;
  initializing: boolean;
  login: (input: LoginInput) => Promise<string | null>;
  verifyMfa: (challengeToken: string, code: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState(false);
  const [initializing, setInitializing] = useState(true);

  useEffect(() => {
    authApi.refreshSession().then((active) => {
      setAuthenticated(active);
      setInitializing(false);
    });
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      authenticated,
      initializing,
      login: async (input) => {
        const challenge = await authApi.login(input);
        if (challenge) return challenge;
        setAuthenticated(true);
        return null;
      },
      verifyMfa: async (challengeToken, code) => {
        await authApi.verifyMfa(challengeToken, code, navigator.userAgent);
        setAuthenticated(true);
      },
      logout: async () => {
        await authApi.logout();
        setAuthenticated(false);
      },
    }),
    [authenticated, initializing],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

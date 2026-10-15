import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { apiFetch, setUnauthorizedHandler, tokenStore } from "@/api/client";
import { ROLES, type LoginResponse, type Role } from "@/api/types";

export interface User {
  username: string;
  role: Role;
}

export class UnknownRoleError extends Error {}

const USER_KEY = "rca.user";

function savedUser(): User | null {
  if (!tokenStore.get()) return null;
  try {
    const value = JSON.parse(sessionStorage.getItem(USER_KEY) ?? "null") as User | null;
    return value && ROLES.includes(value.role) ? value : null;
  } catch {
    return null;
  }
}

interface Auth {
  user: User | null;
  /** True after the server refused the token: the login page says the session ended. */
  sessionEnded: boolean;
  signIn: (username: string, password: string) => Promise<User>;
  signOut: () => void;
}

const AuthContext = createContext<Auth | null>(null);

/** The user comes from the login answer only (POST /auth/login). The token and the user live in
 * sessionStorage: they last as long as the browser tab, like the Streamlit session did. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(savedUser);
  const [sessionEnded, setSessionEnded] = useState(false);

  const clear = useCallback(() => {
    tokenStore.set(null);
    try {
      sessionStorage.removeItem(USER_KEY);
    } catch {
      // nothing saved
    }
    setUser(null);
    queryClient.clear();
  }, [queryClient]);

  const signOut = useCallback(() => {
    setSessionEnded(false);
    clear();
  }, [clear]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setSessionEnded(true);
      clear();
    });
    return () => setUnauthorizedHandler(null);
  }, [clear]);

  const signIn = useCallback(async (username: string, password: string) => {
    const answer = await apiFetch<LoginResponse>("/auth/login", { method: "POST", json: { username, password } });
    if (!ROLES.includes(answer.role as Role)) throw new UnknownRoleError(answer.role);
    const next: User = { username: answer.username, role: answer.role as Role };
    tokenStore.set(answer.access_token);
    try {
      sessionStorage.setItem(USER_KEY, JSON.stringify(next));
    } catch {
      // the session lasts until reload
    }
    setSessionEnded(false);
    setUser(next);
    return next;
  }, []);

  const value = useMemo(() => ({ user, sessionEnded, signIn, signOut }), [user, sessionEnded, signIn, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): Auth {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth is used outside AuthProvider");
  return context;
}

/** The signed-in user, on pages that only render behind the guard. */
export function useUser(): User {
  const { user } = useAuth();
  if (!user) throw new Error("useUser without a signed-in user");
  return user;
}

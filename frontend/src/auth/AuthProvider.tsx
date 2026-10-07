import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { authApi } from "../api/auth";
import { setUnauthorizedListener } from "../api/client";
import type { AuthUser } from "../api/types";
import { Login } from "../pages/Login";
import { AuthContext } from "./context";

/** Gates the app behind a login: renders its children only while a user is
 * logged in, and the login screen otherwise. */
export function AuthProvider({ children }: { children: ReactNode }) {
  // undefined: still asking the server who we are. null: nobody.
  const [user, setUser] = useState<AuthUser | null | undefined>(undefined);

  const refresh = useCallback(async () => {
    try {
      setUser(await authApi.me());
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    setUnauthorizedListener(() => setUser(null));
    return () => setUnauthorizedListener(null);
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // Whatever the server made of it, this browser is done with the session.
    }
    setUser(null);
  }, []);

  const value = useMemo(() => (user ? { user, logout, refresh } : null), [user, logout, refresh]);

  if (user === undefined) return null;
  if (value === null) return <Login onAuthenticated={setUser} />;
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

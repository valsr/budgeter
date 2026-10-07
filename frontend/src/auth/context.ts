import { createContext, useContext } from "react";
import type { AuthUser } from "../api/types";

export interface AuthContextValue {
  user: AuthUser;
  logout: () => Promise<void>;
  /** Re-read the current user from the server (e.g. after an admin change
   * that may have touched the caller's own account). */
  refresh: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

/** The logged-in user. Only usable beneath AuthProvider, which renders its
 * children solely while somebody is logged in — so `user` is never null. */
export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (value === null) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

import type { ReactNode } from "react";
import { AuthContext } from "../auth/context";
import type { AuthUser } from "../api/types";

const TEST_USER: AuthUser = { id: 1, username: "alice", is_admin: true };

/** Stands in for AuthProvider in tests: a logged-in user, no network. */
export function TestAuth({
  children,
  user = TEST_USER,
  logout = async () => {},
  refresh = async () => {},
}: {
  children: ReactNode;
  user?: AuthUser;
  logout?: () => Promise<void>;
  refresh?: () => Promise<void>;
}) {
  return <AuthContext.Provider value={{ user, logout, refresh }}>{children}</AuthContext.Provider>;
}

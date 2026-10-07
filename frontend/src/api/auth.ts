import { apiFetch } from "./client";
import type { AuthStatus, AuthUser } from "./types";

const credentials = (username: string, password: string) => JSON.stringify({ username, password });

// The session probe and the login form report their own failures (a login
// screen, an inline message), so none of these raise the global error toast.
const SILENT = { silent: true };

export const authApi = {
  status: () => apiFetch<AuthStatus>("/api/auth/status", {}, SILENT),
  me: () => apiFetch<AuthUser>("/api/auth/me", {}, SILENT),
  login: (username: string, password: string) =>
    apiFetch<AuthUser>("/api/auth/login", { method: "POST", body: credentials(username, password) }, SILENT),
  register: (username: string, password: string) =>
    apiFetch<AuthUser>("/api/auth/register", { method: "POST", body: credentials(username, password) }, SILENT),
  logout: () => apiFetch<void>("/api/auth/logout", { method: "POST" }, SILENT),
  changePassword: (currentPassword: string, newPassword: string) =>
    apiFetch<void>(
      "/api/auth/password",
      { method: "POST", body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) },
      SILENT,
    ),
  deleteMe: (password: string) =>
    apiFetch<void>("/api/auth/me", { method: "DELETE", body: JSON.stringify({ password }) }, SILENT),
};

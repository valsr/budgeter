import { apiDownload, apiFetch, apiUpload } from "./client";
import type { RequestOpts } from "./client";
import type { AdminUser } from "./types";
import type { VersionInfo } from "./version";

export interface ServerSettings {
  registration_open: boolean;
  port: number;
  ssl_enabled: boolean;
  ssl_certfile: string | null;
  ssl_keyfile: string | null;
  /** Whether the running server was started in a way that applies the port
   * and SSL settings (the launcher), rather than a bare `uvicorn` command. */
  managed: boolean;
  /** The saved port/SSL settings differ from what is being served. */
  restart_required: boolean;
  /** BUDGETER_PORT, when set — it wins over `port`. */
  port_override: number | null;
  /** BUDGETER_SSL_DISABLED — SSL stays off whatever `ssl_enabled` says. */
  ssl_disabled_override: boolean;
}

export type ServerSettingsPatch = Partial<
  Pick<ServerSettings, "registration_open" | "port" | "ssl_enabled" | "ssl_certfile" | "ssl_keyfile">
>;

export interface ServerHealth {
  status: "ok" | "degraded";
  version: VersionInfo;
  /** Each is "ok", "disabled", or a description of what is wrong. */
  checks: Record<string, string>;
  started_at: string;
  uptime_seconds: number;
  /** Null when the server wasn't started through the launcher. */
  serving: { port: number; https: boolean } | null;
  restart_required: boolean;
  users: { total: number; active_admins: number; disabled: number };
  data_dir: string | null;
  storage: { books_files: number; books_bytes: number; server_db_bytes: number } | null;
  schema: { server: string | null; books: string | null } | null;
  python_version: string;
}

export const adminApi = {
  listUsers: () => apiFetch<AdminUser[]>("/api/admin/users"),
  createUser: (username: string, password: string) =>
    apiFetch<AdminUser>("/api/admin/users", { method: "POST", body: JSON.stringify({ username, password }) }),
  updateUser: (id: number, patch: { is_admin?: boolean; is_disabled?: boolean; password?: string }) =>
    apiFetch<AdminUser>(`/api/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteUser: (id: number) => apiFetch<void>(`/api/admin/users/${id}`, { method: "DELETE" }),
  getSettings: () => apiFetch<ServerSettings>("/api/admin/settings"),
  /** Only the fields given change. `silent`: the caller shows the refusal inline. */
  updateSettings: (patch: ServerSettingsPatch, opts?: RequestOpts) =>
    apiFetch<ServerSettings>("/api/admin/settings", { method: "PATCH", body: JSON.stringify(patch) }, opts),
  getHealth: () => apiFetch<ServerHealth>("/api/admin/health"),
  downloadBackup: () => apiDownload("/api/admin/backup"),
  restoreBackup: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiUpload<void>("/api/admin/backup/restore", form);
  },
};

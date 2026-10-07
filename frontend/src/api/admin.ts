import { apiDownload, apiFetch, apiUpload } from "./client";
import type { AdminUser } from "./types";

export interface ServerSettings {
  registration_open: boolean;
}

export const adminApi = {
  listUsers: () => apiFetch<AdminUser[]>("/api/admin/users"),
  createUser: (username: string, password: string) =>
    apiFetch<AdminUser>("/api/admin/users", { method: "POST", body: JSON.stringify({ username, password }) }),
  updateUser: (id: number, patch: { is_admin?: boolean; is_disabled?: boolean; password?: string }) =>
    apiFetch<AdminUser>(`/api/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteUser: (id: number) => apiFetch<void>(`/api/admin/users/${id}`, { method: "DELETE" }),
  getSettings: () => apiFetch<ServerSettings>("/api/admin/settings"),
  updateSettings: (settings: ServerSettings) =>
    apiFetch<ServerSettings>("/api/admin/settings", { method: "PATCH", body: JSON.stringify(settings) }),
  downloadBackup: () => apiDownload("/api/admin/backup"),
  restoreBackup: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiUpload<void>("/api/admin/backup/restore", form);
  },
};

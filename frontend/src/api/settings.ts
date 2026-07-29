import { apiFetch } from "./client";

export const settingsApi = {
  getApiKey: () => apiFetch<{ api_key: string }>("/api/settings/api-key"),
  regenerateApiKey: () =>
    apiFetch<{ api_key: string }>("/api/settings/api-key/regenerate", { method: "POST" }),
  getRetention: () => apiFetch<{ retention_days: number }>("/api/settings/retention"),
  updateRetention: (retentionDays: number) =>
    apiFetch<{ retention_days: number }>("/api/settings/retention", {
      method: "PATCH",
      body: JSON.stringify({ retention_days: retentionDays }),
    }),
};

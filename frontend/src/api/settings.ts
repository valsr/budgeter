import { apiFetch } from "./client";

export const settingsApi = {
  getApiKey: () => apiFetch<{ api_key: string }>("/api/settings/api-key"),
  regenerateApiKey: () =>
    apiFetch<{ api_key: string }>("/api/settings/api-key/regenerate", { method: "POST" }),
};

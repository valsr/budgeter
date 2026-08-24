import { apiFetch, apiUpload } from "./client";
import type {
  DetectAccountsOverride,
  DetectAccountsResponse,
  ImportBatch,
  ImportResolutionInput,
  ReviewQueueItem,
} from "./types";

export const importsApi = {
  list: () => apiFetch<ImportBatch[]>("/api/import"),
  detectAccounts: (file: File, overrides?: DetectAccountsOverride[]) => {
    const form = new FormData();
    form.append("file", file);
    if (overrides) form.append("overrides", JSON.stringify({ overrides }));
    return apiUpload<DetectAccountsResponse>("/api/import/detect-accounts", form);
  },
  commit: (file: File, resolutions: ImportResolutionInput[]) => {
    const form = new FormData();
    form.append("file", file);
    form.append("resolutions", JSON.stringify({ resolutions }));
    return apiUpload<ImportBatch[]>("/api/import/commit", form);
  },
  reviewItems: (batchId?: number, pendingOnly = true) => {
    const params = new URLSearchParams({ pending_only: String(pendingOnly) });
    if (batchId !== undefined) params.set("batch_id", String(batchId));
    return apiFetch<ReviewQueueItem[]>(`/api/import/review-queue/items?${params}`);
  },
  resolveReviewItem: (itemId: number, action: "new" | "merge" | "skip") =>
    apiFetch<ReviewQueueItem>(`/api/import/review-queue/${itemId}/resolve`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),
};

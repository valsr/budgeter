import { apiFetch, apiUploadFile } from "./client";
import type {
  DetectAccountsOverride,
  DetectAccountsResponse,
  ImportBatch,
  ImportResolutionInput,
  ReviewQueueItem,
} from "./types";

export const importsApi = {
  list: () => apiFetch<ImportBatch[]>("/api/import"),
  detectAccounts: (file: File, overrides?: DetectAccountsOverride[]) =>
    apiUploadFile<DetectAccountsResponse>(
      "/api/import/detect-accounts",
      file,
      overrides ? { overrides: JSON.stringify({ overrides }) } : {},
    ),
  commit: (file: File, resolutions: ImportResolutionInput[]) =>
    apiUploadFile<ImportBatch[]>("/api/import/commit", file, { resolutions: JSON.stringify({ resolutions }) }),
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

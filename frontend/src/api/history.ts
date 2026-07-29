import { apiFetch } from "./client";
import type { ChangeEntityType, HistoryPage, UndoResult } from "./types";

export interface HistoryListParams {
  entityType?: ChangeEntityType;
  dateFrom?: string;
  dateTo?: string;
  page?: number;
  pageSize?: number;
}

export function buildQuery(params: HistoryListParams): string {
  const q = new URLSearchParams();
  if (params.entityType) q.set("entity_type", params.entityType);
  if (params.dateFrom) q.set("date_from", params.dateFrom);
  if (params.dateTo) q.set("date_to", params.dateTo);
  q.set("page", String(params.page ?? 1));
  q.set("page_size", String(params.pageSize ?? 50));
  return q.toString();
}

export const historyApi = {
  list: (params: HistoryListParams = {}) => apiFetch<HistoryPage>(`/api/history?${buildQuery(params)}`),
  undo: (groupIds: string[]) =>
    apiFetch<{ results: UndoResult[] }>("/api/history/undo", {
      method: "POST",
      body: JSON.stringify({ group_ids: groupIds }),
    }),
};

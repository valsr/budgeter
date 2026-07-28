import { apiFetch } from "./client";
import type { Split, Transaction, TransactionPage } from "./types";

export interface TransactionFilters {
  account_id?: number;
  date_from?: string;
  date_to?: string;
  amount_min?: number;
  amount_max?: number;
  name_contains?: string;
  category_id?: number;
  page?: number;
  page_size?: number;
  show_categorized?: boolean;
  show_uncategorized?: boolean;
}

export interface SplitInput {
  category_id: number | null;
  amount: number;
}

function buildQuery(filters: TransactionFilters): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export const transactionsApi = {
  list: (filters: TransactionFilters = {}) =>
    apiFetch<TransactionPage>(`/api/transactions${buildQuery(filters)}`),
  get: (id: number) => apiFetch<Transaction>(`/api/transactions/${id}`),
  create: (input: { account_id: number; date: string; name: string; splits: SplitInput[] }) =>
    apiFetch<Transaction>("/api/transactions", { method: "POST", body: JSON.stringify(input) }),
  update: (id: number, input: { date?: string; name?: string }) =>
    apiFetch<Transaction>(`/api/transactions/${id}`, { method: "PATCH", body: JSON.stringify(input) }),
  updateSplits: (id: number, splits: SplitInput[]) =>
    apiFetch<Transaction>(`/api/transactions/${id}/splits`, {
      method: "PUT",
      body: JSON.stringify({ splits }),
    }),
  remove: (id: number) => apiFetch<void>(`/api/transactions/${id}`, { method: "DELETE" }),
  createTransfer: (input: {
    from_account_id: number;
    to_account_id: number;
    date: string;
    name: string;
    amount: number;
  }) =>
    apiFetch<Transaction[]>("/api/transactions/transfer", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  uncategorizedCount: () => apiFetch<{ count: number }>("/api/transactions/uncategorized-count"),
  acceptSuggestion: (transactionId: number, splitId: number) =>
    apiFetch<Split>(`/api/transactions/${transactionId}/splits/${splitId}/accept-suggestion`, {
      method: "POST",
    }),
  rejectSuggestion: (transactionId: number, splitId: number) =>
    apiFetch<Split>(`/api/transactions/${transactionId}/splits/${splitId}/reject-suggestion`, {
      method: "POST",
    }),
};

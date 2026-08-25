import { apiFetch } from "./client";
import type { Budget, ReportRow } from "./types";

export interface BudgetCategoryInput {
  category_id: number;
  monthly_amounts: Record<number, number>;
  /** Narrows this line to one source account. Omit to budget the category as
   * a whole — a category uses one mode or the other, never both. */
  account_id?: number | null;
}

export interface BudgetInput {
  name: string;
  year: number;
  categories: BudgetCategoryInput[];
}

export const budgetsApi = {
  list: () => apiFetch<Budget[]>("/api/budgets"),
  get: (id: number) => apiFetch<Budget>(`/api/budgets/${id}`),
  create: (input: BudgetInput) =>
    apiFetch<Budget>("/api/budgets", { method: "POST", body: JSON.stringify(input) }),
  update: (id: number, input: Partial<BudgetInput>) =>
    apiFetch<Budget>(`/api/budgets/${id}`, { method: "PATCH", body: JSON.stringify(input) }),
  remove: (id: number) => apiFetch<void>(`/api/budgets/${id}`, { method: "DELETE" }),
  /** `accountIds` narrows the report to those source accounts; omit or pass an
   * empty list for all of them. */
  report: (id: number, year: number, throughMonth: number, accountIds?: number[]) => {
    const params = new URLSearchParams({ year: String(year), through_month: String(throughMonth) });
    for (const accountId of accountIds ?? []) params.append("account_id", String(accountId));
    return apiFetch<ReportRow[]>(`/api/budgets/${id}/report?${params}`);
  },
};

export const overviewApi = {
  get: (year: number, throughMonth: number) =>
    apiFetch<ReportRow[]>(`/api/overview?year=${year}&through_month=${throughMonth}`),
};

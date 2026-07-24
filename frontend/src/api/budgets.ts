import { apiFetch } from "./client";
import type { Budget, ReportRow } from "./types";

export interface BudgetCategoryInput {
  category_id: number;
  monthly_amounts: Record<number, number>;
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
  report: (id: number, year: number, throughMonth: number) =>
    apiFetch<ReportRow[]>(`/api/budgets/${id}/report?year=${year}&through_month=${throughMonth}`),
};

export const overviewApi = {
  get: (year: number, throughMonth: number) =>
    apiFetch<ReportRow[]>(`/api/overview?year=${year}&through_month=${throughMonth}`),
};

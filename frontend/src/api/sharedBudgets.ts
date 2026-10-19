import { apiFetch } from "./client";
import type {
  DirectoryUser,
  SharedAmount,
  SharedBudget,
  SharedCategory,
  SharedLink,
  SharedReportRow,
} from "./types";

export interface SharedCategoryInput {
  name: string;
  parent_id?: number | null;
  is_income?: boolean;
}

export type SharedCategoryPatch = Partial<SharedCategoryInput> & {
  sort_order?: number;
  archived?: boolean;
};

/** `amount: null` clears that month's figure. */
export interface SharedAmountLine {
  shared_category_id: number;
  month: number;
  amount: number | null;
}

const json = (method: string, body: unknown) => ({ method, body: JSON.stringify(body) });

export const sharedBudgetsApi = {
  list: () => apiFetch<SharedBudget[]>("/api/shared-budgets"),
  get: (id: number) => apiFetch<SharedBudget>(`/api/shared-budgets/${id}`),
  create: (input: { name: string; member_ids: number[] }) =>
    apiFetch<SharedBudget>("/api/shared-budgets", json("POST", input)),
  rename: (id: number, name: string) =>
    apiFetch<SharedBudget>(`/api/shared-budgets/${id}`, json("PATCH", { name })),
  remove: (id: number) => apiFetch<void>(`/api/shared-budgets/${id}`, { method: "DELETE" }),
  setMembers: (id: number, userIds: number[]) =>
    apiFetch<SharedBudget>(`/api/shared-budgets/${id}/members`, json("PUT", { user_ids: userIds })),
  categories: (id: number) => apiFetch<SharedCategory[]>(`/api/shared-budgets/${id}/categories`),
  createCategory: (id: number, input: SharedCategoryInput) =>
    apiFetch<SharedCategory>(`/api/shared-budgets/${id}/categories`, json("POST", input)),
  updateCategory: (id: number, categoryId: number, patch: SharedCategoryPatch) =>
    apiFetch<SharedCategory>(`/api/shared-budgets/${id}/categories/${categoryId}`, json("PATCH", patch)),
  deleteCategory: (id: number, categoryId: number) =>
    apiFetch<void>(`/api/shared-budgets/${id}/categories/${categoryId}`, { method: "DELETE" }),
  amounts: (id: number, year: number) =>
    apiFetch<SharedAmount[]>(`/api/shared-budgets/${id}/amounts?year=${year}`),
  setAmounts: (id: number, year: number, lines: SharedAmountLine[]) =>
    apiFetch<SharedAmount[]>(`/api/shared-budgets/${id}/amounts`, json("PUT", { year, lines })),
  links: (id: number) => apiFetch<SharedLink[]>(`/api/shared-budgets/${id}/links`),
  setLinks: (id: number, links: SharedLink[]) =>
    apiFetch<SharedLink[]>(`/api/shared-budgets/${id}/links`, json("PUT", { links })),
  report: (id: number, year: number, throughMonth: number) =>
    apiFetch<SharedReportRow[]>(
      `/api/shared-budgets/${id}/report?year=${year}&through_month=${throughMonth}`,
    ),
  directory: () => apiFetch<DirectoryUser[]>("/api/users/directory"),
};

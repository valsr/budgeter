import { apiFetch } from "./client";
import type { Category } from "./types";

export interface CategoryInput {
  name: string;
  parent_id?: number | null;
  color?: string | null;
}

export const categoriesApi = {
  list: (includeArchived = false) =>
    apiFetch<Category[]>(`/api/categories?include_archived=${includeArchived}`),
  create: (input: CategoryInput) =>
    apiFetch<Category>("/api/categories", { method: "POST", body: JSON.stringify(input) }),
  update: (id: number, input: Partial<CategoryInput> & { move_to_root?: boolean }) =>
    apiFetch<Category>(`/api/categories/${id}`, { method: "PATCH", body: JSON.stringify(input) }),
  archive: (id: number) => apiFetch<Category>(`/api/categories/${id}/archive`, { method: "POST" }),
  reorder: (parent_id: number | null, ordered_ids: number[]) =>
    apiFetch<Category[]>("/api/categories/reorder", {
      method: "POST",
      body: JSON.stringify({ parent_id, ordered_ids }),
    }),
};

/** Strip archived categories from a tree fetched with include_archived=true.
 * Pages fetch the full tree so archived categories still render on historical
 * transactions (§2.2), but pickers/filters must only offer active ones. */
export function activeCategories(tree: Category[]): Category[] {
  return tree
    .filter((c) => c.archived_at === null)
    .map((c) => ({ ...c, children: c.children.filter((child) => child.archived_at === null) }));
}

/** Flatten the category tree into leaf-path entries (e.g. "shared:groceries") for pickers. */
export function flattenLeafCategories(tree: Category[]): { id: number; path: string; color: string }[] {
  const result: { id: number; path: string; color: string }[] = [];
  for (const parent of tree) {
    if (parent.children.length === 0) {
      result.push({ id: parent.id, path: parent.name, color: parent.color });
    }
    for (const child of parent.children) {
      result.push({ id: child.id, path: `${parent.name}:${child.name}`, color: child.color });
    }
  }
  return result;
}

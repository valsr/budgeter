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
  /** Find-or-create a category by a colon-delimited path, e.g.
   * "shared:groceries:alcohol" — creates any missing segments and returns
   * the resolved leaf category. */
  resolvePath: (path: string) =>
    apiFetch<Category>("/api/categories/resolve", { method: "POST", body: JSON.stringify({ path }) }),
};

/** Strip archived categories from a tree fetched with include_archived=true.
 * Pages fetch the full tree so archived categories still render on historical
 * transactions (§2.2), but pickers/filters must only offer active ones. */
export function activeCategories(tree: Category[]): Category[] {
  return tree
    .filter((c) => c.archived_at === null)
    .map((c) => ({ ...c, children: c.children.filter((child) => child.archived_at === null) }));
}

export interface CategoryOption {
  id: number;
  path: string;
  depth: number;
  color: string;
  isLeaf: boolean;
}

/** Flatten the category tree into every category (not just leaves), with
 * full colon-joined paths and each node's depth (0 = top level) — used for
 * pickers that need to choose any category, e.g. a new parent or a rollup
 * filter, rather than just leaves. */
export function flattenAllCategories(tree: Category[]): CategoryOption[] {
  const result: CategoryOption[] = [];
  function walk(nodes: Category[], prefix: string, depth: number) {
    for (const node of nodes) {
      const path = prefix ? `${prefix}:${node.name}` : node.name;
      result.push({ id: node.id, path, depth, color: node.color, isLeaf: node.children.length === 0 });
      walk(node.children, path, depth + 1);
    }
  }
  walk(tree, "", 0);
  return result;
}

/** Flatten the category tree into leaf-path entries (e.g.
 * "shared:groceries:alcohol") for pickers — categories can nest to any
 * depth, so this recurses rather than assuming a fixed number of levels.
 * Only leaves (no children) are included: parent categories are never
 * directly assignable, since their totals are always derived from children. */
export function flattenLeafCategories(tree: Category[]): { id: number; path: string; color: string }[] {
  const result: { id: number; path: string; color: string }[] = [];
  function walk(nodes: Category[], prefix: string) {
    for (const node of nodes) {
      const path = prefix ? `${prefix}:${node.name}` : node.name;
      if (node.children.length === 0) {
        result.push({ id: node.id, path, color: node.color });
      } else {
        walk(node.children, path);
      }
    }
  }
  walk(tree, "");
  return result;
}

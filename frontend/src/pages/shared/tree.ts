import type { SharedCategory } from "../../api/types";

export const MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const CURRENT_YEAR = new Date().getFullYear();
/** The years the report and amounts pickers offer. */
export const YEARS = Array.from({ length: 7 }, (_, i) => CURRENT_YEAR - 5 + i);

export interface SharedNode {
  category: SharedCategory;
  depth: number;
  /** "Parent:Child" — for pickers that list the whole tree flat. */
  path: string;
}

/** The shared tree flattened depth-first, siblings in sort order then by name. */
export function sharedTreeOrder(categories: SharedCategory[]): SharedNode[] {
  const childrenOf = new Map<number | null, SharedCategory[]>();
  for (const c of categories) childrenOf.set(c.parent_id, [...(childrenOf.get(c.parent_id) ?? []), c]);
  const out: SharedNode[] = [];
  function walk(parentId: number | null, depth: number, prefix: string) {
    const kids = [...(childrenOf.get(parentId) ?? [])].sort(
      (a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name),
    );
    for (const c of kids) {
      const path = prefix ? `${prefix}:${c.name}` : c.name;
      out.push({ category: c, depth, path });
      walk(c.id, depth + 1, path);
    }
  }
  walk(null, 0, "");
  return out;
}

/** The ids of `id` and everything beneath it — not valid new parents for it. */
export function subtreeIds(categories: SharedCategory[], id: number): Set<number> {
  const ids = new Set([id]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const c of categories) {
      if (c.parent_id !== null && ids.has(c.parent_id) && !ids.has(c.id)) {
        ids.add(c.id);
        grew = true;
      }
    }
  }
  return ids;
}

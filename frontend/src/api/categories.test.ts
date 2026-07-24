import { describe, expect, it } from "vitest";
import { flattenLeafCategories } from "./categories";
import type { Category } from "./types";

function cat(overrides: Partial<Category>): Category {
  return { id: 1, name: "x", parent_id: null, color: "#000", sort_order: 0, archived_at: null, children: [], ...overrides };
}

describe("flattenLeafCategories", () => {
  it("includes childless top-level categories as leaves", () => {
    const tree = [cat({ id: 1, name: "misc", children: [] })];
    expect(flattenLeafCategories(tree)).toEqual([{ id: 1, path: "misc", color: "#000" }]);
  });

  it("excludes parents with children, includes children with parent:child path", () => {
    const tree = [
      cat({
        id: 1,
        name: "shared",
        children: [cat({ id: 2, name: "groceries", parent_id: 1, color: "#111" })],
      }),
    ];
    const result = flattenLeafCategories(tree);
    expect(result).toEqual([{ id: 2, path: "shared:groceries", color: "#111" }]);
  });

  it("handles a mix of standalone leaves and parent groups", () => {
    const tree = [
      cat({ id: 1, name: "shared", children: [cat({ id: 2, name: "groceries", parent_id: 1 })] }),
      cat({ id: 3, name: "misc", children: [] }),
    ];
    const result = flattenLeafCategories(tree);
    expect(result.map((r) => r.path)).toEqual(["shared:groceries", "misc"]);
  });

  it("returns an empty list for an empty tree", () => {
    expect(flattenLeafCategories([])).toEqual([]);
  });
});

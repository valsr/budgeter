import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { categoriesApi, flattenAllCategories, flattenLeafCategories } from "../api/categories";
import type { Category } from "../api/types";
import type { CategoryOption } from "../api/categories";

type Row = { kind: "clear" } | { kind: "option"; option: CategoryOption } | { kind: "create" };

interface CategoryComboboxProps {
  categories: Category[];
  value: number | null;
  onChange: (categoryId: number | null) => void;
  /** "assign" offers a "+ Create '<path>'" row (via POST /api/categories/resolve)
   * when the typed path has no exact match; "filter" only ever searches/selects
   * existing categories. */
  mode?: "assign" | "filter";
  /** "leaves" (default for assign) only offers leaf categories — the only
   * ones a transaction can actually be assigned to. "all" (default for
   * filter) also offers parent categories, matching the rollup filter
   * ("filtering by a parent includes its children") the old plain <select>
   * exposed via a "(all)" suffix. */
  optionSource?: "leaves" | "all";
  /** Label for the "no category" row, shown when the input is empty (e.g.
   * "Unassigned" for assignment, "All categories" for a filter). Omit to
   * disable this row entirely. */
  clearLabel?: string;
  placeholder?: string;
  /** Called after a new category is created via this input, so the caller
   * can refresh whatever category tree it holds. */
  onCreated?: () => void;
  autoFocus?: boolean;
}

/** Colon-delimited category search/create combobox — type a path like
 * "shared:groceries:alcohol" to filter down to it; in "assign" mode, a
 * path with no match offers to create it (and any missing ancestors). */
export function CategoryCombobox({
  categories,
  value,
  onChange,
  mode = "assign",
  optionSource = mode === "filter" ? "all" : "leaves",
  clearLabel,
  placeholder,
  onCreated,
  autoFocus,
}: CategoryComboboxProps) {
  const options = useMemo(() => {
    if (optionSource === "all") return flattenAllCategories(categories);
    return flattenLeafCategories(categories).map((o) => ({ ...o, depth: 0, isLeaf: true }));
  }, [categories, optionSource]);
  const selected = value !== null ? options.find((o) => o.id === value) ?? null : null;

  const [query, setQuery] = useState(selected?.path ?? "");
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const creatingRef = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Keep the displayed text in sync with the externally-controlled value
  // (e.g. after a save elsewhere) while the menu is closed; don't fight the
  // user's typing while it's open.
  useEffect(() => {
    if (!open) setQuery(selected?.path ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const trimmedQuery = query.trim();
  const filtered = trimmedQuery
    ? options.filter((o) => o.path.toLowerCase().includes(trimmedQuery.toLowerCase()))
    : options;
  const exactMatch = trimmedQuery
    ? (options.find((o) => o.path.toLowerCase() === trimmedQuery.toLowerCase()) ?? null)
    : null;
  const canCreate = mode === "assign" && trimmedQuery !== "" && exactMatch === null;

  const rows: Row[] = [
    ...(clearLabel !== undefined && trimmedQuery === "" ? [{ kind: "clear" } as const] : []),
    ...filtered.map((option): Row => ({ kind: "option", option })),
    ...(canCreate ? [{ kind: "create" } as const] : []),
  ];

  function revert() {
    setQuery(selected?.path ?? "");
    setOpen(false);
  }

  function commitSelection(id: number | null) {
    onChange(id);
    const opt = id !== null ? options.find((o) => o.id === id) : null;
    setQuery(opt?.path ?? "");
    setOpen(false);
  }

  async function commitCreate() {
    if (creatingRef.current || trimmedQuery === "") return;
    creatingRef.current = true;
    try {
      const created = await categoriesApi.resolvePath(trimmedQuery);
      onChange(created.id);
      onCreated?.();
      setOpen(false);
    } finally {
      creatingRef.current = false;
    }
  }

  function selectRow(row: Row) {
    if (row.kind === "clear") commitSelection(null);
    else if (row.kind === "option") commitSelection(row.option.id);
    else void commitCreate();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") {
      revert();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setHighlighted((h) => Math.min(h + 1, rows.length - 1));
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlighted((h) => Math.max(h - 1, 0));
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      const row = rows[highlighted] ?? rows[0];
      if (row) selectRow(row);
    }
  }

  return (
    <div className="cat-combobox" ref={containerRef}>
      <input
        autoFocus={autoFocus}
        value={query}
        placeholder={placeholder ?? (mode === "filter" ? "Search categories…" : "Type to search or create…")}
        onFocus={(e) => {
          e.target.select();
          setOpen(true);
          setHighlighted(0);
        }}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          setHighlighted(0);
        }}
        onKeyDown={handleKeyDown}
        onBlur={revert}
      />
      {open && (
        <div className="cat-combobox-menu">
          {rows.length === 0 && <div className="cat-combobox-empty">No matches</div>}
          {rows.map((row, i) => {
            const highlightCls = i === highlighted ? " highlighted" : "";
            if (row.kind === "clear") {
              return (
                <div
                  key="__clear"
                  className={"cat-combobox-option" + highlightCls}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    selectRow(row);
                  }}
                >
                  {clearLabel}
                </div>
              );
            }
            if (row.kind === "create") {
              return (
                <div
                  key="__create"
                  className={"cat-combobox-option cat-combobox-create" + highlightCls}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    selectRow(row);
                  }}
                >
                  + Create "{trimmedQuery}"
                </div>
              );
            }
            return (
              <div
                key={row.option.id}
                className={"cat-combobox-option" + highlightCls}
                onMouseDown={(e) => {
                  e.preventDefault();
                  selectRow(row);
                }}
              >
                <span className="dot" style={{ background: row.option.color }}></span>
                {row.option.path}
                {!row.option.isLeaf && <span className="sub">&nbsp;(all)</span>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

import { useEffect, useRef, useState } from "react";
import type { Account } from "../api/types";

interface AccountFilterProps {
  accounts: Account[];
  /** Empty means every account — a report over no accounts has nothing to
   * show, so "none selected" isn't a distinct state worth having. */
  selectedIds: number[];
  onChange: (ids: number[]) => void;
}

function label(accounts: Account[], selectedIds: number[]): string {
  if (selectedIds.length === 0 || selectedIds.length === accounts.length) return "All accounts";
  if (selectedIds.length === 1) {
    return accounts.find((a) => a.id === selectedIds[0])?.name ?? "1 account";
  }
  return `${selectedIds.length} accounts`;
}

/** Multi-select for narrowing the budget report to a subset of source
 * accounts. A popover of checkboxes rather than a native `<select multiple>`,
 * which hides that more than one can be picked and needs a modifier key. */
export function AccountFilter({ accounts, selectedIds, onChange }: AccountFilterProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const selected = new Set(selectedIds);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  function toggle(accountId: number) {
    // An empty selection renders as every box ticked, so a click there means
    // "deselect this one" -- start from the full set, not from nothing, or
    // unticking a box would select it instead.
    const next =
      selected.size === 0 ? new Set(accounts.map((a) => a.id)) : new Set(selected);
    if (next.has(accountId)) next.delete(accountId);
    else next.add(accountId);
    // A report over no accounts has nothing to show, so the last box can't be
    // unticked; and every account selected is the same report as none, so it
    // normalises to the empty list and the label reads "All accounts".
    if (next.size === 0) return;
    onChange(next.size === accounts.length ? [] : [...next]);
  }

  return (
    <div className="account-filter" ref={rootRef}>
      <button
        type="button"
        className="btn ghost sm"
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
      >
        {label(accounts, selectedIds)} ▾
      </button>
      {open && (
        <div className="account-filter-menu">
          {accounts.map((a) => (
            <label key={a.id} className="account-filter-item">
              <input
                type="checkbox"
                checked={selected.size === 0 || selected.has(a.id)}
                onChange={() => toggle(a.id)}
              />
              {a.name}
            </label>
          ))}
          {selectedIds.length > 0 && (
            <button type="button" className="btn ghost sm" onClick={() => onChange([])}>
              All accounts
            </button>
          )}
        </div>
      )}
    </div>
  );
}

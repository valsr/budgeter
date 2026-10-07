import { useState } from "react";
import { activeCategories, flattenLeafCategories } from "../api/categories";
import { transactionsApi } from "../api/transactions";
import type { Category, Transaction } from "../api/types";
import { formatMoney } from "../format";
import { CategoryCombobox } from "./CategoryCombobox";
import { Modal } from "./Modal";
import { useLearnCheck } from "./Toast";

interface SplitModalProps {
  transaction: Transaction;
  categories: Category[];
  onClose: () => void;
  onSaved: () => void;
}

interface SplitRow {
  category_id: number | null;
  /** Both columns hold positive text; at most one is filled per row. */
  deposit: string;
  withdraw: string;
}

const toCents = (n: number) => Math.round(n * 100);

/** A signed amount as a row's two columns: negative is a withdrawal. */
function amountColumns(amount: number): Pick<SplitRow, "deposit" | "withdraw"> {
  const text = Math.abs(amount).toFixed(2);
  return amount < 0 ? { deposit: "", withdraw: text } : { deposit: text, withdraw: "" };
}

/** Signed cents for a row. A negative typed into either column counts toward
 * the other one straight away, before blur moves it across. */
function rowCents(row: SplitRow): number {
  return toCents(parseFloat(row.deposit) || 0) - toCents(parseFloat(row.withdraw) || 0);
}

const direction = (cents: number) => (cents < 0 ? "withdraw" : "deposit");

export function SplitModal({ transaction, categories, onClose, onSaved }: SplitModalProps) {
  const activeTree = activeCategories(categories);
  const totalCents = transaction.splits.reduce((sum, s) => sum + toCents(s.amount), 0);
  const [rows, setRows] = useState<SplitRow[]>(
    transaction.splits.map((s) => ({ category_id: s.category_id, ...amountColumns(s.amount) })),
  );
  const [error, setError] = useState<string | null>(null);
  const runLearnCheck = useLearnCheck();

  const remainingCents = totalCents - rows.reduce((acc, r) => acc + rowCents(r), 0);
  const matches = remainingCents === 0;

  function updateRow(index: number, patch: Partial<SplitRow>) {
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  function setAmount(index: number, column: "deposit" | "withdraw", value: string) {
    const other = column === "deposit" ? "withdraw" : "deposit";
    updateRow(index, value === "" ? { [column]: value } : { [column]: value, [other]: "" });
  }

  /** A negative deposit is a withdrawal (and vice versa): once the field is
   * left, move it to the other column as a positive number. */
  function normalizeAmount(index: number, column: "deposit" | "withdraw") {
    const value = parseFloat(rows[index][column]);
    if (!(value < 0)) return;
    const other = column === "deposit" ? "withdraw" : "deposit";
    updateRow(index, { [column]: "", [other]: Math.abs(value).toFixed(2) });
  }

  function addRow() {
    const firstLeaf = flattenLeafCategories(activeTree)[0]?.id ?? null;
    // Start the new row on whatever is still unallocated, so the common
    // two-way split is one edit plus one click.
    const columns = matches
      ? { deposit: "", withdraw: "", [direction(totalCents)]: "0.00" }
      : amountColumns(remainingCents / 100);
    setRows((prev) => [...prev, { category_id: firstLeaf, ...columns }]);
  }

  function removeRow(index: number) {
    setRows((prev) => prev.filter((_, i) => i !== index));
  }

  async function save() {
    try {
      await transactionsApi.updateSplits(
        transaction.id,
        rows.map((r) => ({ category_id: r.category_id, amount: rowCents(r) / 100 })),
      );
      onSaved();
      onClose();
      if (rows.length === 1 && rows[0].category_id !== null) {
        runLearnCheck(transaction.id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save splits");
    }
  }

  return (
    <Modal
      title="Split transaction"
      onClose={onClose}
      onSubmit={save}
      submitLabel="Save splits"
      submitDisabled={!matches}
    >
      <p className="sub" style={{ marginBottom: 12 }}>
        {transaction.name} · {formatMoney(totalCents / 100)} {direction(totalCents)}
      </p>
      <div className="cond-row split-head">
        <span style={{ flex: 1 }}>Category</span>
        <span className="split-amount">Deposit</span>
        <span className="split-amount">Withdraw</span>
        {rows.length > 1 && <span className="icon-btn remove split-head-spacer" aria-hidden="true" />}
      </div>
      {rows.map((row, i) => (
        <div className="cond-row" key={i}>
          <CategoryCombobox
            categories={activeTree}
            value={row.category_id}
            onChange={(categoryId) => updateRow(i, { category_id: categoryId })}
            clearLabel="Unassigned"
          />
          {(["deposit", "withdraw"] as const).map((column) => (
            <input
              key={column}
              className="split-amount"
              aria-label={column === "deposit" ? "Deposit" : "Withdraw"}
              inputMode="decimal"
              value={row[column]}
              onChange={(e) => setAmount(i, column, e.target.value)}
              onBlur={() => normalizeAmount(i, column)}
            />
          ))}
          {rows.length > 1 && (
            <span className="icon-btn remove" onClick={() => removeRow(i)}>
              🗑
            </span>
          )}
        </div>
      ))}
      <button type="button" className="btn ghost sm" onClick={addRow}>
        + Add split
      </button>
      <p
        className="sub"
        data-testid="split-remaining"
        style={{ marginTop: 10, color: matches ? undefined : "var(--c5)" }}
      >
        {matches
          ? "Balanced — nothing left to allocate."
          : `Remaining: ${formatMoney(remainingCents / 100)} ${direction(remainingCents)}`}
      </p>
      {error && (
        <p className="sub" data-testid="split-error" style={{ color: "var(--c5)" }}>
          {error}
        </p>
      )}
    </Modal>
  );
}

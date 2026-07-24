import { useState } from "react";
import { flattenLeafCategories } from "../api/categories";
import { transactionsApi } from "../api/transactions";
import type { Category, Transaction } from "../api/types";
import { Modal } from "./Modal";

interface SplitModalProps {
  transaction: Transaction;
  categories: Category[];
  onClose: () => void;
  onSaved: () => void;
}

export function SplitModal({ transaction, categories, onClose, onSaved }: SplitModalProps) {
  const leafCategories = flattenLeafCategories(categories);
  const total = transaction.splits.reduce((sum, s) => sum + s.amount, 0);
  const [rows, setRows] = useState(
    transaction.splits.map((s) => ({ category_id: s.category_id, amount: String(s.amount) })),
  );
  const [error, setError] = useState<string | null>(null);

  const sum = rows.reduce((acc, r) => acc + (parseFloat(r.amount) || 0), 0);
  const matches = Math.abs(sum - total) < 0.005;

  function updateRow(index: number, patch: Partial<{ category_id: number | null; amount: string }>) {
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  function addRow() {
    setRows((prev) => [...prev, { category_id: leafCategories[0]?.id ?? null, amount: "0.00" }]);
  }

  function removeRow(index: number) {
    setRows((prev) => prev.filter((_, i) => i !== index));
  }

  async function save() {
    if (!matches) {
      setError(`Splits must sum to $${Math.abs(total).toFixed(2)}`);
      return;
    }
    try {
      await transactionsApi.updateSplits(
        transaction.id,
        rows.map((r) => ({ category_id: r.category_id, amount: parseFloat(r.amount) || 0 })),
      );
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save splits");
    }
  }

  return (
    <Modal title="Split transaction" onClose={onClose} onSubmit={save} submitLabel="Save splits">
      <p className="sub" style={{ marginBottom: 12 }}>
        {transaction.name} · ${Math.abs(total).toFixed(2)} total
      </p>
      {rows.map((row, i) => (
        <div className="cond-row" key={i}>
          <select
            value={row.category_id ?? ""}
            onChange={(e) => updateRow(i, { category_id: e.target.value === "" ? null : Number(e.target.value) })}
          >
            <option value="">Unassigned</option>
            {leafCategories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.path}
              </option>
            ))}
          </select>
          <input
            value={row.amount}
            style={{ width: 90 }}
            onChange={(e) => updateRow(i, { amount: e.target.value })}
          />
          {rows.length > 1 && (
            <span className="icon-btn remove" onClick={() => removeRow(i)}>
              ⌀
            </span>
          )}
        </div>
      ))}
      <button type="button" className="btn ghost sm" onClick={addRow}>
        + Add split
      </button>
      <p className="sub" style={{ marginTop: 10 }}>
        Splits must sum to ${Math.abs(total).toFixed(2)}. Current sum: ${Math.abs(sum).toFixed(2)}
      </p>
      {error && (
        <p className="sub" data-testid="split-error" style={{ color: "var(--c5)" }}>
          {error}
        </p>
      )}
    </Modal>
  );
}

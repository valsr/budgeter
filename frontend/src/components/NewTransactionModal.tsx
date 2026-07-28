import { useState } from "react";
import { activeCategories, flattenLeafCategories } from "../api/categories";
import { transactionsApi } from "../api/transactions";
import type { Account, Category } from "../api/types";
import { Modal } from "./Modal";
import { useLearnCheck } from "./Toast";

interface NewTransactionModalProps {
  accounts: Account[];
  categories: Category[];
  defaultAccountId?: number;
  onClose: () => void;
  onSaved: () => void;
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function NewTransactionModal({
  accounts,
  categories,
  defaultAccountId,
  onClose,
  onSaved,
}: NewTransactionModalProps) {
  const leafCategories = flattenLeafCategories(activeCategories(categories));
  const [accountId, setAccountId] = useState<number | "">(defaultAccountId ?? accounts[0]?.id ?? "");
  const [date, setDate] = useState(today());
  const [name, setName] = useState("");
  const [categoryId, setCategoryId] = useState<number | "">("");
  const [kind, setKind] = useState<"withdraw" | "deposit">("withdraw");
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string | null>(null);
  const runLearnCheck = useLearnCheck();

  async function save() {
    if (accountId === "") {
      setError("Choose an account");
      return;
    }
    if (!name.trim()) {
      setError("Enter a name");
      return;
    }
    const magnitude = parseFloat(amount);
    if (!magnitude || magnitude <= 0) {
      setError("Enter an amount greater than 0");
      return;
    }
    const signedAmount = kind === "withdraw" ? -magnitude : magnitude;
    try {
      const created = await transactionsApi.create({
        account_id: accountId,
        date,
        name: name.trim(),
        splits: [{ category_id: categoryId === "" ? null : categoryId, amount: signedAmount }],
      });
      onSaved();
      onClose();
      if (categoryId !== "") {
        runLearnCheck(created.id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create transaction");
    }
  }

  return (
    <Modal title="New transaction" onClose={onClose} onSubmit={save} submitLabel="Create transaction">
      <div className="field">
        <label>Account</label>
        <select value={accountId} onChange={(e) => setAccountId(e.target.value === "" ? "" : Number(e.target.value))}>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label>Date</label>
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </div>
      <div className="field">
        <label>Name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Trader Joe's" />
      </div>
      <div className="field">
        <label>Category</label>
        <select value={categoryId} onChange={(e) => setCategoryId(e.target.value === "" ? "" : Number(e.target.value))}>
          <option value="">Unassigned</option>
          {leafCategories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.path}
            </option>
          ))}
        </select>
      </div>
      <div className="cond-row">
        <select value={kind} onChange={(e) => setKind(e.target.value as "withdraw" | "deposit")} style={{ maxWidth: 140 }}>
          <option value="withdraw">Withdraw</option>
          <option value="deposit">Deposit</option>
        </select>
        <input
          placeholder="Amount"
          style={{ flex: 1 }}
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
      </div>
      {error && (
        <p className="sub" style={{ color: "var(--c5)" }}>
          {error}
        </p>
      )}
    </Modal>
  );
}

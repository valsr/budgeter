import { useEffect, useMemo, useState } from "react";
import { transactionsApi } from "../api/transactions";
import { flattenLeafCategories } from "../api/categories";
import type { Account, Category, Split, Transaction } from "../api/types";
import { CategoryTag } from "./CategoryTag";

interface TransactionTableProps {
  categories: Category[];
  accounts: Account[];
  lockAccountId?: number;
  onSplitTransaction?: (transaction: Transaction) => void;
  refreshKey?: number;
  onDataChanged?: () => void;
}

interface Filters {
  name_contains: string;
  date_from: string;
  date_to: string;
  amount_min: string;
  amount_max: string;
  category_id: string;
  account_id: string;
}

const EMPTY_FILTERS: Filters = {
  name_contains: "",
  date_from: "",
  date_to: "",
  amount_min: "",
  amount_max: "",
  category_id: "",
  account_id: "",
};

const PAGE_SIZE = 100;

export function TransactionTable({
  categories,
  accounts,
  lockAccountId,
  onSplitTransaction,
  refreshKey,
  onDataChanged,
}: TransactionTableProps) {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<{ items: Transaction[]; total: number } | null>(null);
  const [editingSplit, setEditingSplit] = useState<{ txnId: number; splitId: number } | null>(null);

  const leafCategories = useMemo(() => flattenLeafCategories(categories), [categories]);
  const categoryById = useMemo(() => {
    const map = new Map<number, { name: string; color: string }>();
    for (const parent of categories) {
      map.set(parent.id, { name: parent.name, color: parent.color });
      for (const child of parent.children) {
        map.set(child.id, { name: child.name, color: child.color });
      }
    }
    return map;
  }, [categories]);
  const accountById = useMemo(() => new Map(accounts.map((a) => [a.id, a])), [accounts]);

  const showAccountColumn = lockAccountId === undefined;

  async function load() {
    const res = await transactionsApi.list({
      account_id: lockAccountId ?? (filters.account_id ? Number(filters.account_id) : undefined),
      date_from: filters.date_from || undefined,
      date_to: filters.date_to || undefined,
      amount_min: filters.amount_min ? Number(filters.amount_min) : undefined,
      amount_max: filters.amount_max ? Number(filters.amount_max) : undefined,
      name_contains: filters.name_contains || undefined,
      category_id: filters.category_id ? Number(filters.category_id) : undefined,
      page,
      page_size: PAGE_SIZE,
    });
    setData({ items: res.items, total: res.total });
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, page, lockAccountId, refreshKey]);

  useEffect(() => {
    setPage(1);
  }, [filters, lockAccountId]);

  async function assignCategory(transactionId: number, splitId: number, categoryId: number | null) {
    const txn = data?.items.find((t) => t.id === transactionId);
    const split = txn?.splits.find((s) => s.id === splitId);
    if (!txn || !split) return;
    const otherSplits = txn.splits.filter((s) => s.id !== splitId);
    await transactionsApi.updateSplits(transactionId, [
      ...otherSplits.map((s) => ({ category_id: s.category_id, amount: s.amount })),
      { category_id: categoryId, amount: split.amount },
    ]);
    setEditingSplit(null);
    load();
    onDataChanged?.();
  }

  async function accept(transactionId: number, splitId: number) {
    await transactionsApi.acceptSuggestion(transactionId, splitId);
    load();
    onDataChanged?.();
  }

  async function reject(transactionId: number, splitId: number) {
    await transactionsApi.rejectSuggestion(transactionId, splitId);
    load();
    onDataChanged?.();
  }

  function renderCategoryCell(txn: Transaction, split: Split) {
    if (txn.type === "transfer") {
      return (
        <td>
          <span className="tag" style={{ background: "#eee", color: "#777" }}>
            transfer
          </span>
        </td>
      );
    }

    const isEditing = editingSplit?.txnId === txn.id && editingSplit?.splitId === split.id;
    if (isEditing) {
      return (
        <td>
          <select
            className="cat-edit-input"
            autoFocus
            defaultValue={split.category_id ?? ""}
            onBlur={() => setEditingSplit(null)}
            onChange={(e) => {
              const value = e.target.value;
              assignCategory(txn.id, split.id, value === "" ? null : Number(value));
            }}
          >
            <option value="">Unassigned</option>
            {leafCategories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.path}
              </option>
            ))}
          </select>
        </td>
      );
    }

    if (split.suggested_category_id !== null) {
      const cat = categoryById.get(split.suggested_category_id);
      return (
        <td>
          <span className="cat-suggest">{cat?.name ?? "?"}?</span>
          <span
            className="icon-btn accept"
            title="Accept"
            onClick={(e) => {
              e.stopPropagation();
              accept(txn.id, split.id);
            }}
          >
            ✓
          </span>
          <span
            className="icon-btn reject"
            title="Reject"
            onClick={(e) => {
              e.stopPropagation();
              reject(txn.id, split.id);
            }}
          >
            ✗
          </span>
        </td>
      );
    }

    if (split.category_id === null) {
      return (
        <td className="cat-cell" onClick={() => setEditingSplit({ txnId: txn.id, splitId: split.id })}>
          <button type="button" className="btn ghost sm cat-assign-btn">
            + Assign category
          </button>
        </td>
      );
    }

    const cat = categoryById.get(split.category_id);
    return (
      <td className="cat-cell" onClick={() => setEditingSplit({ txnId: txn.id, splitId: split.id })}>
        {cat ? <CategoryTag label={cat.name} color={cat.color} /> : split.category_id}
      </td>
    );
  }

  function renderAmountCells(amount: number) {
    return (
      <>
        <td className="right">{amount > 0 ? `$${amount.toFixed(2)}` : "—"}</td>
        <td className="right">{amount < 0 ? `$${Math.abs(amount).toFixed(2)}` : "—"}</td>
      </>
    );
  }

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div>
      <div className="filters-2row">
        <div className="filters-row">
          <input
            placeholder="Search name…"
            style={{ width: 200 }}
            value={filters.name_contains}
            onChange={(e) => setFilters((f) => ({ ...f, name_contains: e.target.value }))}
          />
          <input
            type="date"
            title="From date"
            value={filters.date_from}
            onChange={(e) => setFilters((f) => ({ ...f, date_from: e.target.value }))}
          />
          <input
            type="date"
            title="To date"
            value={filters.date_to}
            onChange={(e) => setFilters((f) => ({ ...f, date_to: e.target.value }))}
          />
          <input
            placeholder="Min amount"
            style={{ width: 100 }}
            value={filters.amount_min}
            onChange={(e) => setFilters((f) => ({ ...f, amount_min: e.target.value }))}
          />
          <input
            placeholder="Max amount"
            style={{ width: 100 }}
            value={filters.amount_max}
            onChange={(e) => setFilters((f) => ({ ...f, amount_max: e.target.value }))}
          />
        </div>
        <div className="filters-row">
          <select
            value={filters.category_id}
            onChange={(e) => setFilters((f) => ({ ...f, category_id: e.target.value }))}
          >
            <option value="">All categories</option>
            {categories.map((parent) => (
              <optgroup key={parent.id} label={parent.name}>
                <option value={parent.id}>{parent.name} (all)</option>
                {parent.children.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
          {showAccountColumn && (
            <select
              value={filters.account_id}
              onChange={(e) => setFilters((f) => ({ ...f, account_id: e.target.value }))}
            >
              <option value="">All accounts</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Name</th>
            {showAccountColumn && <th>Account</th>}
            <th>Category</th>
            <th className="right">Deposit</th>
            <th className="right">Withdraw</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((txn) => {
            const account = accountById.get(txn.account_id);
            const accountTag = account ? (
              <span className="tag" style={{ background: "#dfeef1", color: "#4f8a9c" }}>
                {account.name}
              </span>
            ) : null;

            if (txn.splits.length === 1) {
              const split = txn.splits[0];
              const isUncat = split.category_id === null;
              const rowClass = isUncat ? "uncat-a" + (split.suggested_category_id !== null ? " suggest-row" : "") : "";
              return (
                <tr key={txn.id} className={rowClass}>
                  <td>{txn.date}</td>
                  <td>{txn.name}</td>
                  {showAccountColumn && <td>{accountTag}</td>}
                  {renderCategoryCell(txn, split)}
                  {renderAmountCells(split.amount)}
                  <td className="ctrl-cell">
                    {txn.type === "normal" && onSplitTransaction && (
                      <span
                        className="icon-btn split"
                        title="Split transaction"
                        onClick={() => onSplitTransaction(txn)}
                      >
                        ✂
                      </span>
                    )}
                  </td>
                </tr>
              );
            }

            return txn.splits.map((split, i) => {
              const last = i === txn.splits.length - 1;
              return (
                <tr key={split.id} className={"grouped" + (last ? " last" : "")}>
                  <td>{i === 0 ? txn.date : ""}</td>
                  <td className="name-cell">{i === 0 ? txn.name : "↳ split"}</td>
                  {showAccountColumn && <td>{i === 0 ? accountTag : ""}</td>}
                  {renderCategoryCell(txn, split)}
                  {renderAmountCells(split.amount)}
                  <td className="ctrl-cell">
                    {i === 0 && onSplitTransaction && (
                      <span className="icon-btn split" title="Edit split" onClick={() => onSplitTransaction(txn)}>
                        ✎
                      </span>
                    )}
                  </td>
                </tr>
              );
            });
          })}
        </tbody>
      </table>

      <div className="pagination">
        <span>
          Showing {total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total}
        </span>
        <div className="pages">
          <span onClick={() => setPage((p) => Math.max(1, p - 1))}>‹</span>
          <span className="cur">{page}</span>
          {totalPages > 1 && <span>of {totalPages}</span>}
          <span onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>›</span>
        </div>
      </div>
    </div>
  );
}

import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { transactionsApi } from "../api/transactions";
import { activeCategories, flattenAllCategories } from "../api/categories";
import type { Account, Category, Split, Transaction } from "../api/types";
import { CategoryCombobox } from "./CategoryCombobox";
import { CategoryTag, hexToRgba } from "./CategoryTag";
import { LinkTransferModal } from "./LinkTransferModal";
import { NewTransactionModal } from "./NewTransactionModal";
import { useLearnCheck } from "./Toast";

interface TransactionTableProps {
  /** Full category tree including archived (so historical transactions still
   * render their category); pickers/filters use only the active subset. */
  categories: Category[];
  accounts: Account[];
  lockAccountId?: number;
  onSplitTransaction?: (transaction: Transaction) => void;
  refreshKey?: number;
  onDataChanged?: () => void;
  /** Called after a category is created on the fly via the assign/filter
   * combobox, so the caller can refetch its category tree. */
  onCategoriesChanged?: () => void;
  initialFilters?: Partial<Filters>;
  /** Extra controls rendered in the filter row, right-aligned immediately
   * left of "+ New transaction" (e.g. the Transactions page's "Run rules"). */
  filterRowExtra?: ReactNode;
}

export interface Filters {
  name_contains: string;
  date_from: string;
  date_to: string;
  amount_min: string;
  amount_max: string;
  category_id: string;
  account_id: string;
  show_categorized: boolean;
  show_uncategorized: boolean;
}

const EMPTY_FILTERS: Filters = {
  name_contains: "",
  date_from: "",
  date_to: "",
  amount_min: "",
  amount_max: "",
  category_id: "",
  account_id: "",
  show_categorized: true,
  show_uncategorized: true,
};

const PAGE_SIZE = 100;
const DEFAULT_ACCOUNT_COLOR = "#4f8a9c";

/** One line in the table. A linked transfer is a single movement of money
 * shown once, with a leg in each of two accounts; everything else is one
 * transaction on one account. */
type Entry =
  | { kind: "single"; txn: Transaction }
  | { kind: "pair"; from: Transaction; to: Transaction; carrying: Transaction };

function totalOf(txn: Transaction): number {
  return txn.splits.reduce((sum, s) => sum + s.amount, 0);
}

/** The leg holding the pair's category. A pair carries its category on
 * exactly one leg (both would net the movement to zero), and which leg sets
 * the sign the category sees — so an uncategorized pair defaults to the
 * withdrawal leg, whose amount is negative and therefore reads as spending. */
function carryingLeg(from: Transaction, to: Transaction): Transaction {
  return to.splits.some((s) => s.category_id !== null) ? to : from;
}

/** Whether the entry still needs categorizing — mirrors the server's
 * _is_uncategorized_clause. A pair counts as uncategorized only when neither
 * leg carries a category: the non-carrying leg's empty split is the model
 * working, not a gap. */
function isEntryUncategorized(entry: Entry): boolean {
  if (entry.kind === "pair") {
    return ![entry.from, entry.to].some((leg) =>
      leg.splits.some((s) => s.category_id !== null),
    );
  }
  return entry.txn.splits.some((s) => s.category_id === null);
}

export function TransactionTable({
  categories,
  accounts,
  lockAccountId,
  onSplitTransaction,
  refreshKey,
  onDataChanged,
  onCategoriesChanged,
  initialFilters,
  filterRowExtra,
}: TransactionTableProps) {
  const [filters, setFilters] = useState<Filters>({ ...EMPTY_FILTERS, ...initialFilters });
  const [page, setPage] = useState(1);
  const [data, setData] = useState<{ items: Transaction[]; total: number } | null>(null);
  const [editingSplit, setEditingSplit] = useState<{ txnId: number; splitId: number } | null>(null);
  const [showNewTxnModal, setShowNewTxnModal] = useState(false);
  const [linkingTxn, setLinkingTxn] = useState<Transaction | null>(null);
  const runLearnCheck = useLearnCheck();

  const activeTree = useMemo(() => activeCategories(categories), [categories]);
  const categoryById = useMemo(() => {
    const map = new Map<number, { path: string; color: string }>();
    for (const opt of flattenAllCategories(categories)) {
      map.set(opt.id, { path: opt.path, color: opt.color });
    }
    return map;
  }, [categories]);
  const accountById = useMemo(() => new Map(accounts.map((a) => [a.id, a])), [accounts]);
  const itemById = useMemo(
    () => new Map((data?.items ?? []).map((t) => [t.id, t])),
    [data],
  );

  /** The account whose ledger is being viewed, if any. A linked pair spans two
   * accounts, so its amount only belongs in a Deposit/Withdraw column when
   * there's a single account to be relative to. */
  const viewingAccountId =
    lockAccountId ?? (filters.account_id ? Number(filters.account_id) : undefined);

  // A linked pair is one movement of money and renders as one line. The
  // server guarantees both legs arrive on the same page (it pages by entry,
  // not by row), so pairing up here is always complete -- see
  // transactions.py's _entry_key_expr.
  const entries = useMemo<Entry[]>(() => {
    const rows = data?.items ?? [];
    const byId = new Map(rows.map((t) => [t.id, t]));
    const consumed = new Set<number>();
    const result: Entry[] = [];

    for (const txn of rows) {
      if (consumed.has(txn.id)) continue;
      const pair =
        txn.type === "transfer" && txn.transfer_pair_id !== null
          ? byId.get(txn.transfer_pair_id)
          : undefined;
      if (!pair) {
        result.push({ kind: "single", txn });
        continue;
      }
      consumed.add(txn.id);
      consumed.add(pair.id);
      const [from, to] = totalOf(txn) < 0 ? [txn, pair] : [pair, txn];
      result.push({ kind: "pair", from, to, carrying: carryingLeg(from, to) });
    }
    return result;
  }, [data]);

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
      show_categorized: filters.show_categorized ? undefined : false,
      show_uncategorized: filters.show_uncategorized ? undefined : false,
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
    const priorCategoryId = split.category_id;
    const resultingSplitCount = otherSplits.length + 1;
    await transactionsApi.updateSplits(transactionId, [
      ...otherSplits.map((s) => ({ category_id: s.category_id, amount: s.amount })),
      { category_id: categoryId, amount: split.amount },
    ]);
    setEditingSplit(null);
    load();
    onDataChanged?.();
    if (
      txn.type === "normal" &&
      resultingSplitCount === 1 &&
      categoryId !== null &&
      categoryId !== priorCategoryId
    ) {
      runLearnCheck(transactionId);
    }
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

  async function unlinkTransfer(txn: Transaction) {
    if (
      !confirm(
        `Unlink this transfer — "${txn.name}"? Both transactions stay, but become ordinary uncategorized transactions again.`,
      )
    ) {
      return;
    }
    await transactionsApi.unlinkTransfer(txn.id);
    load();
    onDataChanged?.();
  }

  async function deleteTransaction(txn: Transaction) {
    const total = txn.splits.reduce((sum, s) => sum + s.amount, 0);
    const noun = txn.type === "transfer" ? "transfer (both legs)" : "transaction";
    if (!confirm(`Delete this ${noun} — "${txn.name}", $${Math.abs(total).toFixed(2)}? This can't be undone.`)) {
      return;
    }
    await transactionsApi.remove(txn.id);
    load();
    onDataChanged?.();
  }

  function renderCategoryCell(txn: Transaction, split: Split) {
    const isEditing = editingSplit?.txnId === txn.id && editingSplit?.splitId === split.id;
    if (isEditing) {
      return (
        <td
          onBlur={(e) => {
            // Only cancel editing once focus has genuinely left the cell —
            // clicking a dropdown row keeps the combobox's input focused
            // (see CategoryCombobox's mousedown/preventDefault), so this
            // won't fire for a real selection, only for a click-away.
            if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
              setEditingSplit(null);
            }
          }}
        >
          <CategoryCombobox
            categories={activeTree}
            value={split.category_id}
            onChange={(categoryId) => assignCategory(txn.id, split.id, categoryId)}
            clearLabel="Unassigned"
            onCreated={onCategoriesChanged}
            autoFocus
          />
        </td>
      );
    }

    if (split.suggested_category_id !== null) {
      const cat = categoryById.get(split.suggested_category_id);
      const tooltip =
        split.suggestion_source === "ai"
          ? "Suggested by AI — accept to confirm or reject to clear"
          : "Suggested by a categorization rule — accept to confirm or reject to clear";
      return (
        <td>
          <span className="cat-suggest" title={tooltip}>{cat?.path ?? "?"}?</span>
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
        {cat ? (
          <CategoryTag
            label={cat.path}
            color={cat.color}
            onRemove={() => assignCategory(txn.id, split.id, null)}
          />
        ) : (
          split.category_id
        )}
      </td>
    );
  }

  /** Transfers carry a ⇄ before the name so a linked pair is recognisable in
   * the list itself, not only by opening the row. Where the other leg happens
   * to be on the same page the tooltip names its account; otherwise only the
   * pair's existence is known here (the row carries an id, not the pair). */
  function renderName(txn: Transaction) {
    if (txn.type !== "transfer") return txn.name;

    const pair = txn.transfer_pair_id === null ? undefined : itemById.get(txn.transfer_pair_id);
    const pairAccount = pair ? accountById.get(pair.account_id) : undefined;
    const title =
      txn.transfer_pair_id === null
        ? "Transfer with no matching transaction linked"
        : pairAccount
          ? `Transfer — paired with ${pairAccount.name}`
          : "Transfer — paired with a transaction on another account";

    return (
      <>
        <span className="transfer-mark" title={title} aria-label={title}>
          ⇄
        </span>
        {txn.name}
      </>
    );
  }

  function accountTagFor(accountId: number) {
    const account = accountById.get(accountId);
    if (!account) return null;
    const color = account.color ?? DEFAULT_ACCOUNT_COLOR;
    return (
      <span className="tag" style={{ background: hexToRgba(color, 0.15), color }}>
        {account.name}
      </span>
    );
  }

  /** A linked pair on one line: where the money went, and the one category it
   * counts under. */
  function renderPairRow(entry: Extract<Entry, { kind: "pair" }>, rowClass: string) {
    const { from, to, carrying } = entry;
    const amount = Math.abs(totalOf(from));
    // Deposit/Withdraw are account-relative, so they only mean something when
    // a single account is in view. Otherwise the from → to arrow carries the
    // direction and the amount spans both columns.
    const viewedLeg =
      viewingAccountId === undefined
        ? undefined
        : [from, to].find((leg) => leg.account_id === viewingAccountId);

    return (
      <tr key={`pair-${from.id}-${to.id}`} className={("transfer-row " + rowClass).trim()}>
        <td>{from.date}</td>
        <td title={`Other leg: ${to.name}`}>
          <span className="transfer-mark" aria-label="Linked transfer">
            ⇄
          </span>
          {from.name}
        </td>
        {showAccountColumn && (
          <td className="transfer-accounts">
            {accountTagFor(from.account_id)}
            <span className="transfer-arrow">→</span>
            {accountTagFor(to.account_id)}
          </td>
        )}
        {renderCategoryCell(carrying, carrying.splits[0])}
        {viewedLeg ? (
          renderAmountCells(totalOf(viewedLeg))
        ) : (
          <td className="right transfer-amount" colSpan={2}>
            ${amount.toFixed(2)}
          </td>
        )}
        <td className="ctrl-cell">
          <span
            className="icon-btn unlink"
            title="Unlink transfer — turn both legs back into ordinary transactions"
            onClick={() => unlinkTransfer(from)}
          >
            ⛓
          </span>
          <span
            className="icon-btn remove"
            title="Delete transfer (both legs)"
            onClick={() => deleteTransaction(from)}
          >
            🗑
          </span>
        </td>
      </tr>
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
          <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
            {filterRowExtra}
            <button className="btn sm" onClick={() => setShowNewTxnModal(true)}>
              + New transaction
            </button>
          </div>
        </div>
        <div className="filters-row">
          <CategoryCombobox
            categories={activeTree}
            value={filters.category_id ? Number(filters.category_id) : null}
            onChange={(categoryId) =>
              setFilters((f) => ({ ...f, category_id: categoryId === null ? "" : String(categoryId) }))
            }
            mode="filter"
            clearLabel="All categories"
            placeholder="All categories"
          />
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
          <div className="toggle-group">
            <button
              type="button"
              className={"toggle-btn" + (filters.show_categorized ? " on" : "")}
              onClick={() => setFilters((f) => ({ ...f, show_categorized: !f.show_categorized }))}
            >
              Categorized
            </button>
            <button
              type="button"
              className={"toggle-btn" + (filters.show_uncategorized ? " on" : "")}
              onClick={() => setFilters((f) => ({ ...f, show_uncategorized: !f.show_uncategorized }))}
            >
              Uncategorized
            </button>
          </div>
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
          {(() => {
            // Wireframe alternates uncat-a/uncat-b backgrounds across
            // consecutive uncategorized rows; track the count while rendering.
            let uncatCounter = 0;
            return entries.map((entry) => {
            let entryClass = "";
            if (isEntryUncategorized(entry)) {
              uncatCounter += 1;
              entryClass = uncatCounter % 2 === 1 ? "uncat-a" : "uncat-b";
            }
            if (entry.kind === "pair") return renderPairRow(entry, entryClass);
            const txn = entry.txn;
            const account = accountById.get(txn.account_id);
            const accountColor = account?.color ?? DEFAULT_ACCOUNT_COLOR;
            const accountTag = account ? (
              <span className="tag" style={{ background: hexToRgba(accountColor, 0.15), color: accountColor }}>
                {account.name}
              </span>
            ) : null;

            if (txn.splits.length === 1) {
              const split = txn.splits[0];
              const rowClass =
                entryClass && split.suggested_category_id !== null
                  ? entryClass + " suggest-row"
                  : entryClass;
              return (
                <tr key={txn.id} className={rowClass}>
                  <td>{txn.date}</td>
                  <td>{renderName(txn)}</td>
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
                    {txn.type === "normal" ? (
                      <span
                        className="icon-btn link"
                        title="Link as transfer — pair this with its other leg on another account"
                        onClick={() => setLinkingTxn(txn)}
                      >
                        🔗
                      </span>
                    ) : (
                      <span
                        className="icon-btn unlink"
                        title="Unlink transfer — turn both legs back into ordinary transactions"
                        onClick={() => unlinkTransfer(txn)}
                      >
                        ⛓
                      </span>
                    )}
                    <span className="icon-btn remove" title="Delete transaction" onClick={() => deleteTransaction(txn)}>
                      🗑
                    </span>
                  </td>
                </tr>
              );
            }

            return txn.splits.map((split, i) => {
              const last = i === txn.splits.length - 1;
              return (
                <tr key={split.id} className={"grouped" + (last ? " last" : "")}>
                  <td>{i === 0 ? txn.date : ""}</td>
                  <td className="name-cell">{i === 0 ? renderName(txn) : "↳ split"}</td>
                  {showAccountColumn && <td>{i === 0 ? accountTag : ""}</td>}
                  {renderCategoryCell(txn, split)}
                  {renderAmountCells(split.amount)}
                  <td className="ctrl-cell">
                    {i === 0 && onSplitTransaction && (
                      <span className="icon-btn split" title="Edit split" onClick={() => onSplitTransaction(txn)}>
                        ✎
                      </span>
                    )}
                    {i === 0 && (
                      <span
                        className="icon-btn remove"
                        title="Delete transaction"
                        onClick={() => deleteTransaction(txn)}
                      >
                        🗑
                      </span>
                    )}
                  </td>
                </tr>
              );
            });
            });
          })()}
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

      {linkingTxn && (
        <LinkTransferModal
          transaction={linkingTxn}
          accounts={accounts}
          onClose={() => setLinkingTxn(null)}
          onLinked={() => {
            setLinkingTxn(null);
            load();
            onDataChanged?.();
          }}
        />
      )}

      {showNewTxnModal && (
        <NewTransactionModal
          accounts={accounts}
          categories={categories}
          defaultAccountId={lockAccountId}
          onClose={() => setShowNewTxnModal(false)}
          onSaved={() => {
            load();
            onDataChanged?.();
          }}
        />
      )}
    </div>
  );
}

import { Fragment, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { budgetsApi, overviewApi } from "../api/budgets";
import type { BudgetCategoryInput } from "../api/budgets";
import { accountsApi } from "../api/accounts";
import { categoriesApi } from "../api/categories";
import type { Account, Budget, Category, DroppedCategory, ReportRow } from "../api/types";
import { AccountFilter } from "../components/AccountFilter";
import { Modal } from "../components/Modal";
import { formatMoney } from "../format";

const MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const now = new Date();
const CURRENT_YEAR = now.getFullYear();
const CURRENT_MONTH = now.getMonth() + 1;

/** Wireframe's monthClass(): odd columns get a light tint, the last (current)
 * month gets a stronger one — matches docs/wireframes.html's renderBudgetReport. */
function monthClass(i: number, total: number): string {
  if (i === total - 1) return "month-current";
  return i % 2 === 1 ? "month-alt" : "";
}

export function Budgets() {
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [currentBudgetId, setCurrentBudgetId] = useState<number | null>(null);
  const [report, setReport] = useState<ReportRow[]>([]);
  const [modalMode, setModalMode] = useState<null | "new" | "edit">(null);
  const [avgByCategory, setAvgByCategory] = useState<Record<number, number>>({});
  const [dropped, setDropped] = useState<DroppedCategory[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  // Empty means every account. Narrows the report to a subset of sources, for
  // working out a budget over just those.
  const [accountFilter, setAccountFilter] = useState<number[]>([]);
  // Report rows are read off one at a time when copying figures into another
  // system, so the row under the eye stays marked until another is picked.
  const [highlightedRow, setHighlightedRow] = useState<string | null>(null);
  // Categories whose per-source breakdown is showing. Collapsed by default —
  // the summary is the primary view and the table is already twelve months
  // wide, so the breakdown is opened for the category being worked on.
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  function loadBudgets() {
    budgetsApi.list().then((list) => {
      setBudgets(list);
      if (currentBudgetId === null && list.length > 0) setCurrentBudgetId(list[0].id);
    });
  }

  useEffect(() => {
    loadBudgets();
    categoriesApi.list().then(setCategories);
    accountsApi.list().then(setAccounts);
    // Actuals across all categories (regardless of budget membership), used
    // for the edit modal's per-category "avg $" hint (docs/wireframes.html AVERAGES).
    overviewApi.get(CURRENT_YEAR, CURRENT_MONTH).then((rows) => {
      const avgs: Record<number, number> = {};
      for (const row of rows) {
        if (row.is_parent) continue;
        const total = Object.values(row.monthly).reduce((sum, m) => sum + m.actual, 0);
        avgs[row.category_id] = total / CURRENT_MONTH;
      }
      setAvgByCategory(avgs);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function loadReport(budgetId: number | null, accountIds: number[] = accountFilter) {
    if (budgetId !== null) {
      budgetsApi.report(budgetId, CURRENT_YEAR, CURRENT_MONTH, accountIds).then(setReport);
    } else {
      setReport([]);
    }
  }

  useEffect(() => {
    loadReport(currentBudgetId);
    setHighlightedRow(null);
    setExpanded(new Set());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentBudgetId]);

  // Live filtering: changing the account selection refetches straight away
  // rather than waiting for an Apply.
  useEffect(() => {
    loadReport(currentBudgetId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accountFilter]);

  // Escape clears it. Clicking the highlighted row again deliberately does
  // *not*, so a stray second click while reading figures across doesn't wipe
  // the marker.
  useEffect(() => {
    if (highlightedRow === null) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setHighlightedRow(null);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [highlightedRow]);

  const currentBudget = budgets.find((b) => b.id === currentBudgetId);
  const months = useMemo(() => Array.from({ length: CURRENT_MONTH }, (_, i) => i + 1), []);

  const categoriesWithBreakdown = useMemo(
    () => new Set(report.filter((r) => r.account_id !== null).map((r) => r.category_id)),
    [report],
  );
  const visibleRows = useMemo(
    () => report.filter((r) => r.account_id === null || expanded.has(r.category_id)),
    [report, expanded],
  );

  function toggleExpanded(categoryId: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(categoryId)) {
        next.delete(categoryId);
        // Don't leave the highlight on a row that just disappeared — move it
        // up to the category the collapsed rows belong to.
        setHighlightedRow((current) =>
          current?.startsWith(`cat:${categoryId}:acct:`) ? `cat:${categoryId}` : current,
        );
      } else {
        next.add(categoryId);
      }
      return next;
    });
  }

  return (
    <div>
      <div className="toolbar">
        <div>
          <h1>Budgets</h1>
          <p className="sub" style={{ marginBottom: 0 }}>
            Pick a budget to see its report, or create a new one.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn ghost" onClick={() => setModalMode("new")}>
            + New budget
          </button>
          <button className="btn" onClick={() => setModalMode("edit")} disabled={!currentBudget}>
            Edit budget
          </button>
        </div>
      </div>

      <div className="filters" style={{ marginBottom: 20, display: "flex", gap: 8, alignItems: "center" }}>
        <select
          value={currentBudgetId ?? ""}
          onChange={(e) => setCurrentBudgetId(e.target.value ? Number(e.target.value) : null)}
        >
          {budgets.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </select>
        {accounts.length > 1 && (
          <AccountFilter
            accounts={accounts}
            selectedIds={accountFilter}
            onChange={setAccountFilter}
          />
        )}
      </div>

      {dropped.length > 0 && (
        <div className="notice" style={{ marginBottom: 16 }}>
          <b>Some categories were dropped from this budget.</b>{" "}
          {dropped.map((d) => describeDropped(d)).join(" ")} Their budgeted amounts are gone; the
          spending itself still counts, under whichever category it now belongs to.
          <button
            type="button"
            className="btn ghost sm"
            style={{ marginLeft: 8 }}
            onClick={() => setDropped([])}
          >
            Dismiss
          </button>
        </div>
      )}

      {currentBudget && (
        <>
          <div className="section-title">
            {currentBudget.name} · Jan → {MONTH_LABELS[CURRENT_MONTH - 1]}
            {accountFilter.length > 0 && (
              <span className="section-note">
                {" · "}
                {accountFilter
                  .map((id) => accounts.find((a) => a.id === id)?.name ?? `#${id}`)
                  .join(", ")}{" "}
                only
              </span>
            )}
          </div>
          <table id="budget-report-table">
            <thead>
              <tr>
                <th rowSpan={2}>Category</th>
                {months.map((m, i) => (
                  <th key={m} colSpan={2} className={"month-label " + monthClass(i, months.length)}>
                    {MONTH_LABELS[m - 1]}
                  </th>
                ))}
                <th rowSpan={2}>YTD diff</th>
              </tr>
              <tr>
                {months.map((m, i) => (
                  <Fragment key={m}>
                    <th className={"sub-col " + monthClass(i, months.length)}>Budgeted</th>
                    <th className={"sub-col " + monthClass(i, months.length)}>Actual</th>
                  </Fragment>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row) => (
                <tr
                  key={row.row_key}
                  className={
                    (highlightedRow === row.row_key ? "row-highlight " : "") +
                    (row.account_id !== null ? "breakdown-row" : "")
                  }
                  style={row.is_parent ? { fontWeight: 600 } : undefined}
                  onClick={() => setHighlightedRow(row.row_key)}
                >
                  <td style={row.depth > 0 ? { paddingLeft: 22 * row.depth, color: "var(--ink-2)" } : undefined}>
                    {row.account_id !== null && <span className="breakdown-mark">↳</span>}
                    {row.account_id === null && categoriesWithBreakdown.has(row.category_id) && (
                      <span
                        className="expander"
                        role="button"
                        aria-expanded={expanded.has(row.category_id)}
                        aria-label={
                          (expanded.has(row.category_id) ? "Hide" : "Show") +
                          ` ${row.name} breakdown by account`
                        }
                        // Stops the row's own click handler running, so
                        // opening a breakdown doesn't also move the highlight.
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleExpanded(row.category_id);
                        }}
                      >
                        {expanded.has(row.category_id) ? "▾" : "▸"}
                      </span>
                    )}
                    {row.name}
                  </td>
                  {months.map((m, i) => {
                    const cell = row.monthly[m] ?? { budgeted: 0, actual: 0 };
                    const over = cell.actual > cell.budgeted;
                    const cls = monthClass(i, months.length);
                    return (
                      <Fragment key={m}>
                        <td className={"right muted-cell " + cls + (cell.budgeted < 0 ? " neg" : "")}>
                          {formatMoney(cell.budgeted)}
                        </td>
                        <td className={"right " + cls + (over ? " over" : cell.actual < 0 ? " neg" : "")}>
                          {formatMoney(cell.actual)}
                        </td>
                      </Fragment>
                    );
                  })}
                  <td className={"right " + (row.ytd_diff >= 0 ? "diff-pos" : "diff-neg")}>
                    {row.has_budget ? formatMoney(row.ytd_diff) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {modalMode && (
        <BudgetModal
          mode={modalMode}
          budget={modalMode === "edit" ? currentBudget ?? null : null}
          categories={categories}
          accounts={accounts}
          avgByCategory={avgByCategory}
          onClose={() => setModalMode(null)}
          onSaved={(id, droppedCategories) => {
            setModalMode(null);
            setDropped(droppedCategories);
            loadBudgets();
            // setCurrentBudgetId is a no-op when editing the already-selected
            // budget (same id in, same id out), which would otherwise leave
            // the report showing pre-edit amounts -- refetch explicitly.
            setCurrentBudgetId(id);
            loadReport(id);
          }}
        />
      )}
    </div>
  );
}

/** Why a category couldn't stay in the budget, in the user's terms — a
 * budget outlives the category tree it was built against. */
function describeDropped(d: DroppedCategory): string {
  const name = d.name === null ? `Category #${d.category_id}` : `"${d.name}"`;
  if (d.reason === "broken_down") return `${name} was split into subcategories — budget those instead.`;
  if (d.reason === "archived") return `${name} was archived.`;
  if (d.reason === "account_removed") return `${name}'s line for a deleted account was removed.`;
  return `${name} was deleted.`;
}

interface BudgetModalProps {
  mode: "new" | "edit";
  budget: Budget | null;
  categories: Category[];
  accounts: Account[];
  avgByCategory: Record<number, number>;
  onClose: () => void;
  onSaved: (budgetId: number, dropped: DroppedCategory[]) => void;
}

/** A category's amounts are keyed by source account, with SOURCE_ALL standing
 * for "the category as a whole". Keeping both in one shape means the month
 * inputs, the save payload, and the totals all take the same path whether or
 * not a category is broken down. */
const SOURCE_ALL = "all";
type MonthAmounts = Record<number, string>;
type CategoryAmounts = Record<string, MonthAmounts>;

function sumMonth(bySource: CategoryAmounts | undefined, month: number): number {
  if (!bySource) return 0;
  return Object.entries(bySource)
    .filter(([source]) => source !== SOURCE_ALL)
    .reduce((total, [, months]) => total + (parseFloat(months[month] ?? "") || 0), 0);
}

function BudgetModal({ mode, budget, categories, accounts, avgByCategory, onClose, onSaved }: BudgetModalProps) {
  const [name, setName] = useState(budget?.name ?? "");
  const [selected, setSelected] = useState<Set<number>>(
    new Set(budget?.budget_categories.map((bc) => bc.category_id) ?? []),
  );
  // Categories planned per source account rather than as a whole.
  const [perAccount, setPerAccount] = useState<Set<number>>(
    new Set(
      (budget?.budget_categories ?? [])
        .filter((bc) => bc.account_id !== null)
        .map((bc) => bc.category_id),
    ),
  );
  const [amounts, setAmounts] = useState<Record<number, CategoryAmounts>>(() => {
    const initial: Record<number, CategoryAmounts> = {};
    for (const bc of budget?.budget_categories ?? []) {
      const source = bc.account_id === null ? SOURCE_ALL : String(bc.account_id);
      const bySource = (initial[bc.category_id] ??= {});
      bySource[source] = {};
      for (const a of bc.amounts) {
        if (a.year === CURRENT_YEAR) bySource[source][a.month] = String(a.amount);
      }
    }
    return initial;
  });

  function toggle(categoryId: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(categoryId)) next.delete(categoryId);
      else next.add(categoryId);
      return next;
    });
  }

  function togglePerAccount(categoryId: number) {
    setPerAccount((prev) => {
      const next = new Set(prev);
      if (next.has(categoryId)) next.delete(categoryId);
      else next.add(categoryId);
      return next;
    });
    // Selecting the breakdown implies budgeting the category.
    setSelected((prev) => new Set(prev).add(categoryId));
  }

  function setAmount(categoryId: number, source: string, month: number, value: string) {
    setAmounts((prev) => ({
      ...prev,
      [categoryId]: {
        ...prev[categoryId],
        [source]: { ...prev[categoryId]?.[source], [month]: value },
      },
    }));
  }

  // Only leaves can be directly budgeted (parent totals are always derived
  // from children); non-leaf categories at any depth render as a plain
  // section header instead of a selectable/amount-entry row.
  function renderCategoryRows(nodes: Category[], depth: number): ReactNode[] {
    const rows: ReactNode[] = [];
    for (const node of nodes) {
      if (node.children.length === 0) {
        const split = perAccount.has(node.id);
        rows.push(
          <tr key={node.id}>
            <td style={{ paddingLeft: 14 + depth * 14, color: "var(--ink-2)" }}>
              <div>{node.name}</div>
              {avgByCategory[node.id] !== undefined && (
                <div className="avg-hint">avg {formatMoney(avgByCategory[node.id])}</div>
              )}
              {accounts.length > 1 && (
                <button
                  type="button"
                  className={"btn ghost sm split-toggle" + (split ? " on" : "")}
                  title="Plan this category separately for each source account"
                  onClick={() => togglePerAccount(node.id)}
                >
                  {split ? "one total" : "per account"}
                </button>
              )}
            </td>
            <td style={{ textAlign: "center" }}>
              <input type="checkbox" checked={selected.has(node.id)} onChange={() => toggle(node.id)} />
            </td>
            {MONTH_LABELS.map((_, i) => {
              const m = i + 1;
              return (
                <td key={m} className={i % 2 === 1 ? "month-alt" : undefined}>
                  {split ? (
                    // Derived from the account rows below, like every other
                    // total in the report — not separately editable.
                    <span className="month-total">{formatMoney(sumMonth(amounts[node.id], m))}</span>
                  ) : (
                    <input
                      className="month-input"
                      value={amounts[node.id]?.[SOURCE_ALL]?.[m] ?? ""}
                      onChange={(e) => setAmount(node.id, SOURCE_ALL, m, e.target.value)}
                    />
                  )}
                </td>
              );
            })}
          </tr>,
        );
        if (split) {
          for (const account of accounts) {
            rows.push(
              <tr key={`${node.id}-${account.id}`} className="breakdown-row">
                <td style={{ paddingLeft: 28 + depth * 14, color: "var(--ink-2)" }}>
                  <span className="breakdown-mark">↳</span>
                  {account.name}
                </td>
                <td />
                {MONTH_LABELS.map((_, i) => {
                  const m = i + 1;
                  return (
                    <td key={m} className={i % 2 === 1 ? "month-alt" : undefined}>
                      <input
                        className="month-input"
                        aria-label={`${node.name} ${account.name} ${MONTH_LABELS[i]}`}
                        value={amounts[node.id]?.[String(account.id)]?.[m] ?? ""}
                        onChange={(e) => setAmount(node.id, String(account.id), m, e.target.value)}
                      />
                    </td>
                  );
                })}
              </tr>,
            );
          }
        }
      } else {
        rows.push(
          <tr key={node.id}>
            <td
              colSpan={14}
              style={{ fontWeight: 600, paddingTop: 12, paddingLeft: depth * 14, borderBottom: "none" }}
            >
              {node.name}
            </td>
          </tr>,
        );
        rows.push(...renderCategoryRows(node.children, depth + 1));
      }
    }
    return rows;
  }

  function monthsFor(categoryId: number, source: string): Record<number, number> {
    const monthly: Record<number, number> = {};
    for (let m = 1; m <= 12; m++) {
      const raw = amounts[categoryId]?.[source]?.[m];
      monthly[m] = raw ? parseFloat(raw) || 0 : 0;
    }
    return monthly;
  }

  async function save() {
    const categoryPayload: BudgetCategoryInput[] = [];
    for (const categoryId of selected) {
      if (!perAccount.has(categoryId)) {
        categoryPayload.push({
          category_id: categoryId,
          account_id: null,
          monthly_amounts: monthsFor(categoryId, SOURCE_ALL),
        });
        continue;
      }
      // One line per account that actually has a plan. An account left blank
      // has no line rather than a line of zeros, so the report doesn't sprout
      // a row for every account the user never budgeted.
      const lines = accounts
        .map((account) => ({
          category_id: categoryId,
          account_id: account.id,
          monthly_amounts: monthsFor(categoryId, String(account.id)),
        }))
        .filter((line) => Object.values(line.monthly_amounts).some((v) => v !== 0));
      if (lines.length > 0) {
        categoryPayload.push(...lines);
      } else {
        // Broken down but nothing entered anywhere: keep the category
        // budgeted rather than silently dropping the selection.
        categoryPayload.push({
          category_id: categoryId,
          account_id: null,
          monthly_amounts: monthsFor(categoryId, SOURCE_ALL),
        });
      }
    }

    if (mode === "new") {
      const created = await budgetsApi.create({ name: name || "Untitled budget", year: CURRENT_YEAR, categories: categoryPayload });
      onSaved(created.id, created.dropped_categories);
    } else if (budget) {
      const saved = await budgetsApi.update(budget.id, { name, year: CURRENT_YEAR, categories: categoryPayload });
      onSaved(budget.id, saved.dropped_categories);
    }
  }

  return (
    <Modal
      title={mode === "edit" ? "Edit budget" : "New budget"}
      onClose={onClose}
      onSubmit={save}
      submitLabel={mode === "edit" ? "Save changes" : "Create budget"}
      width={1280}
    >
      <div className="field">
        <label>Budget name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Household" style={{ maxWidth: 320 }} />
      </div>
      <div className="field">
        <label>Categories — show in this budget, and monthly amounts</label>
        <div style={{ overflowX: "auto" }}>
          <table id="budget-edit-table" style={{ minWidth: 1200 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left" }}>Category</th>
                <th>Show</th>
                {MONTH_LABELS.map((label, i) => (
                  <th key={label} className={"right" + (i % 2 === 1 ? " month-alt" : "")}>
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>{renderCategoryRows(categories, 0)}</tbody>
          </table>
        </div>
      </div>
    </Modal>
  );
}

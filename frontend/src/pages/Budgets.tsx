import { Fragment, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { budgetsApi, overviewApi } from "../api/budgets";
import { categoriesApi } from "../api/categories";
import type { Budget, Category, ReportRow } from "../api/types";
import { Modal } from "../components/Modal";

const MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function fmtMoney(n: number): string {
  const sign = n < 0 ? "-" : "";
  return `${sign}$${Math.abs(n).toFixed(0)}`;
}

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

  function loadBudgets() {
    budgetsApi.list().then((list) => {
      setBudgets(list);
      if (currentBudgetId === null && list.length > 0) setCurrentBudgetId(list[0].id);
    });
  }

  useEffect(() => {
    loadBudgets();
    categoriesApi.list().then(setCategories);
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

  useEffect(() => {
    if (currentBudgetId !== null) {
      budgetsApi.report(currentBudgetId, CURRENT_YEAR, CURRENT_MONTH).then(setReport);
    } else {
      setReport([]);
    }
  }, [currentBudgetId]);

  const currentBudget = budgets.find((b) => b.id === currentBudgetId);
  const months = useMemo(() => Array.from({ length: CURRENT_MONTH }, (_, i) => i + 1), []);

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

      <div className="filters" style={{ marginBottom: 20 }}>
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
      </div>

      {currentBudget && (
        <>
          <div className="section-title">
            {currentBudget.name} · Jan → {MONTH_LABELS[CURRENT_MONTH - 1]}
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
              {report.map((row) => (
                <tr key={row.category_id} style={row.is_parent ? { fontWeight: 600 } : undefined}>
                  <td style={row.depth > 0 ? { paddingLeft: 22 * row.depth, color: "var(--ink-2)" } : undefined}>
                    {row.name}
                  </td>
                  {months.map((m, i) => {
                    const cell = row.monthly[m] ?? { budgeted: 0, actual: 0 };
                    const over = cell.actual > cell.budgeted;
                    const cls = monthClass(i, months.length);
                    return (
                      <Fragment key={m}>
                        <td className={"right muted-cell " + cls}>{cell.budgeted}</td>
                        <td className={"right " + cls + (over ? " over" : "")}>{cell.actual}</td>
                      </Fragment>
                    );
                  })}
                  <td className={"right " + (row.ytd_diff >= 0 ? "diff-pos" : "diff-neg")}>
                    {row.ytd_diff >= 0 ? "+" : ""}
                    {fmtMoney(row.ytd_diff)}
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
          avgByCategory={avgByCategory}
          onClose={() => setModalMode(null)}
          onSaved={(id) => {
            setModalMode(null);
            loadBudgets();
            setCurrentBudgetId(id);
          }}
        />
      )}
    </div>
  );
}

interface BudgetModalProps {
  mode: "new" | "edit";
  budget: Budget | null;
  categories: Category[];
  avgByCategory: Record<number, number>;
  onClose: () => void;
  onSaved: (budgetId: number) => void;
}

function BudgetModal({ mode, budget, categories, avgByCategory, onClose, onSaved }: BudgetModalProps) {
  const [name, setName] = useState(budget?.name ?? "");
  const [selected, setSelected] = useState<Set<number>>(
    new Set(budget?.budget_categories.map((bc) => bc.category_id) ?? []),
  );
  const [amounts, setAmounts] = useState<Record<number, Record<number, string>>>(() => {
    const initial: Record<number, Record<number, string>> = {};
    for (const bc of budget?.budget_categories ?? []) {
      initial[bc.category_id] = {};
      for (const a of bc.amounts) {
        if (a.year === CURRENT_YEAR) initial[bc.category_id][a.month] = String(a.amount);
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

  function setAmount(categoryId: number, month: number, value: string) {
    setAmounts((prev) => ({
      ...prev,
      [categoryId]: { ...prev[categoryId], [month]: value },
    }));
  }

  // Only leaves can be directly budgeted (parent totals are always derived
  // from children); non-leaf categories at any depth render as a plain
  // section header instead of a selectable/amount-entry row.
  function renderCategoryRows(nodes: Category[], depth: number): ReactNode[] {
    const rows: ReactNode[] = [];
    for (const node of nodes) {
      if (node.children.length === 0) {
        rows.push(
          <tr key={node.id}>
            <td style={{ paddingLeft: 14 + depth * 14, color: "var(--ink-2)" }}>
              <div>{node.name}</div>
              {avgByCategory[node.id] !== undefined && (
                <div className="avg-hint">avg ${Math.round(Math.abs(avgByCategory[node.id]))}</div>
              )}
            </td>
            <td style={{ textAlign: "center" }}>
              <input type="checkbox" checked={selected.has(node.id)} onChange={() => toggle(node.id)} />
            </td>
            {MONTH_LABELS.map((_, i) => {
              const m = i + 1;
              return (
                <td key={m} className={i % 2 === 1 ? "month-alt" : undefined}>
                  <input
                    className="month-input"
                    value={amounts[node.id]?.[m] ?? ""}
                    onChange={(e) => setAmount(node.id, m, e.target.value)}
                  />
                </td>
              );
            })}
          </tr>,
        );
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

  async function save() {
    const categoryPayload = Array.from(selected).map((categoryId) => {
      const monthly: Record<number, number> = {};
      for (let m = 1; m <= 12; m++) {
        const raw = amounts[categoryId]?.[m];
        monthly[m] = raw ? parseFloat(raw) || 0 : 0;
      }
      return { category_id: categoryId, monthly_amounts: monthly };
    });

    if (mode === "new") {
      const created = await budgetsApi.create({ name: name || "Untitled budget", year: CURRENT_YEAR, categories: categoryPayload });
      onSaved(created.id);
    } else if (budget) {
      await budgetsApi.update(budget.id, { name, year: CURRENT_YEAR, categories: categoryPayload });
      onSaved(budget.id);
    }
  }

  return (
    <Modal
      title={mode === "edit" ? "Edit budget" : "New budget"}
      onClose={onClose}
      onSubmit={save}
      submitLabel={mode === "edit" ? "Save changes" : "Create budget"}
      wide
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

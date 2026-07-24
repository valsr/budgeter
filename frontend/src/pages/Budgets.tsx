import { Fragment, useEffect, useMemo, useState } from "react";
import { budgetsApi } from "../api/budgets";
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

export function Budgets() {
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [currentBudgetId, setCurrentBudgetId] = useState<number | null>(null);
  const [report, setReport] = useState<ReportRow[]>([]);
  const [modalMode, setModalMode] = useState<null | "new" | "edit">(null);

  function loadBudgets() {
    budgetsApi.list().then((list) => {
      setBudgets(list);
      if (currentBudgetId === null && list.length > 0) setCurrentBudgetId(list[0].id);
    });
  }

  useEffect(() => {
    loadBudgets();
    categoriesApi.list().then(setCategories);
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
          <table>
            <thead>
              <tr>
                <th rowSpan={2}>Category</th>
                {months.map((m) => (
                  <th key={m} colSpan={2} className="month-label">
                    {MONTH_LABELS[m - 1]}
                  </th>
                ))}
                <th rowSpan={2}>YTD diff</th>
              </tr>
              <tr>
                {months.map((m) => (
                  <Fragment key={m}>
                    <th className="sub-col">Budgeted</th>
                    <th className="sub-col">Actual</th>
                  </Fragment>
                ))}
              </tr>
            </thead>
            <tbody>
              {report.map((row) => (
                <tr key={row.category_id} style={row.is_parent ? { fontWeight: 600 } : undefined}>
                  <td style={row.is_parent ? undefined : { paddingLeft: 22, color: "var(--ink-2)" }}>{row.name}</td>
                  {months.map((m) => {
                    const cell = row.monthly[m] ?? { budgeted: 0, actual: 0 };
                    const over = cell.actual > cell.budgeted;
                    return (
                      <Fragment key={m}>
                        <td className="right muted-cell">{cell.budgeted}</td>
                        <td className={"right" + (over ? " over" : "")}>{cell.actual}</td>
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
  onClose: () => void;
  onSaved: (budgetId: number) => void;
}

function BudgetModal({ mode, budget, categories, onClose, onSaved }: BudgetModalProps) {
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
          <table style={{ minWidth: 1200 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left" }}>Category</th>
                <th>Show</th>
                {MONTH_LABELS.map((label) => (
                  <th key={label} className="right">
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {categories.map((parent) => (
                <Fragment key={parent.id}>
                  <tr>
                    <td colSpan={14} style={{ fontWeight: 600, paddingTop: 12, borderBottom: "none" }}>
                      {parent.name}
                    </td>
                  </tr>
                  {parent.children.map((c) => (
                    <tr key={c.id}>
                      <td style={{ paddingLeft: 14, color: "var(--ink-2)" }}>{c.name}</td>
                      <td style={{ textAlign: "center" }}>
                        <input type="checkbox" checked={selected.has(c.id)} onChange={() => toggle(c.id)} />
                      </td>
                      {MONTH_LABELS.map((_, i) => {
                        const m = i + 1;
                        return (
                          <td key={m}>
                            <input
                              className="month-input"
                              value={amounts[c.id]?.[m] ?? ""}
                              onChange={(e) => setAmount(c.id, m, e.target.value)}
                            />
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Modal>
  );
}

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { budgetsApi, overviewApi } from "../api/budgets";
import { categoriesApi } from "../api/categories";
import { transactionsApi } from "../api/transactions";
import type { Budget, ReportRow } from "../api/types";
import { formatMoney } from "../format";

function rowTotals(row: ReportRow): { budgeted: number; actual: number } {
  const months = Object.values(row.monthly);
  return {
    budgeted: months.reduce((sum, m) => sum + m.budgeted, 0),
    actual: months.reduce((sum, m) => sum + m.actual, 0),
  };
}

// The last budget picked here, so the Overview reopens on it: a budget id,
// or "all" for the every-category view.
const BUDGET_STORAGE_KEY = "budgeter.overview.budget";
const ALL_CATEGORIES = "all";

export function Overview() {
  const [rows, setRows] = useState<ReportRow[]>([]);
  const [budgets, setBudgets] = useState<Budget[]>([]);
  // null until the budget list has loaded and the remembered choice resolved.
  const [selection, setSelection] = useState<string | null>(null);
  const [topLevelIds, setTopLevelIds] = useState<Set<number>>(new Set());
  const [uncategorizedCount, setUncategorizedCount] = useState(0);

  useEffect(() => {
    transactionsApi.uncategorizedCount().then((r) => setUncategorizedCount(r.count));
    categoriesApi.list().then((tree) => setTopLevelIds(new Set(tree.map((c) => c.id))));
    budgetsApi.list().then((list) => {
      setBudgets(list);
      const stored = localStorage.getItem(BUDGET_STORAGE_KEY);
      const remembered =
        stored === ALL_CATEGORIES || list.some((b) => String(b.id) === stored) ? stored : null;
      setSelection(remembered ?? (list.length > 0 ? String(list[0].id) : ALL_CATEGORIES));
    });
  }, []);

  useEffect(() => {
    if (selection === null) return;
    const now = new Date();
    const year = now.getFullYear();
    const throughMonth = now.getMonth() + 1;
    const request =
      selection === ALL_CATEGORIES
        ? overviewApi.get(year, throughMonth)
        : budgetsApi.report(Number(selection), year, throughMonth);
    let stale = false;
    // A budget's report also carries per-account breakdown rows; this
    // summary shows one line per category.
    request.then((result) => {
      if (!stale) setRows(result.filter((r) => r.account_id === null));
    });
    return () => {
      stale = true;
    };
  }, [selection]);

  function selectBudget(value: string) {
    setSelection(value);
    localStorage.setItem(BUDGET_STORAGE_KEY, value);
  }

  // Grand total = Σ expense actuals − Σ income actuals, over top-level rows
  // only (parent rollups already fold their children's actuals in, so
  // summing children too would double count). The backend already flips an
  // income-marked category's actual to read as a natural positive "money
  // received" amount (see Category.is_income), so it has to be subtracted
  // back out explicitly here rather than just summed with the rest.
  const grandTotal = rows
    .filter((r) => topLevelIds.has(r.category_id))
    .reduce((sum, r) => sum + (r.is_income ? -rowTotals(r).actual : rowTotals(r).actual), 0);

  return (
    <div>
      <h1>Overview</h1>
      <p className="sub">Category balances, year-to-date budgeted minus actual, following the category hierarchy.</p>

      <div className="field" style={{ maxWidth: 320 }}>
        <label htmlFor="overview-budget">Budget</label>
        <select
          id="overview-budget"
          value={selection ?? ALL_CATEGORIES}
          disabled={selection === null}
          onChange={(e) => selectBudget(e.target.value)}
        >
          {budgets.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
          <option value={ALL_CATEGORIES}>All categories</option>
        </select>
      </div>

      {uncategorizedCount > 0 && (
        <div className="banner">
          <span>{uncategorizedCount} transactions haven't been categorized yet.</span>
          <Link to="/transactions?uncategorized=1">Review them →</Link>
        </div>
      )}

      <table>
        <thead>
          <tr>
            <th>Category</th>
            <th className="right">Budgeted (YTD)</th>
            <th className="right">Actual (YTD)</th>
            <th className="right">Balance</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const { budgeted, actual } = rowTotals(row);
            const balance = row.has_budget ? row.ytd_diff : null;
            return (
              <tr key={row.row_key} style={row.is_parent ? { fontWeight: 600 } : undefined}>
                <td style={row.depth > 0 ? { paddingLeft: 26 * row.depth } : undefined}>{row.name}</td>
                <td className={"right" + (budgeted < 0 ? " neg" : "")}>
                  {row.has_budget ? formatMoney(budgeted) : "—"}
                </td>
                <td className={"right" + (actual < 0 ? " neg" : "")}>{formatMoney(actual)}</td>
                <td className={"right" + (balance !== null && balance < 0 ? " neg" : "")}>
                  {balance !== null ? formatMoney(balance) : "—"}
                </td>
              </tr>
            );
          })}
          <tr style={{ fontWeight: 700, borderTop: "2px solid var(--line-strong)" }}>
            <td>Grand total (expenses − income)</td>
            <td></td>
            <td></td>
            <td className={"right" + (grandTotal < 0 ? " neg" : "")}>{formatMoney(grandTotal)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

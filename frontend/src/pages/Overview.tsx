import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { overviewApi } from "../api/budgets";
import { categoriesApi } from "../api/categories";
import { transactionsApi } from "../api/transactions";
import type { ReportRow } from "../api/types";

function fmtMoney(n: number): string {
  const sign = n < 0 ? "-" : "";
  return `${sign}$${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function rowTotals(row: ReportRow): { budgeted: number; actual: number } {
  const months = Object.values(row.monthly);
  return {
    budgeted: months.reduce((sum, m) => sum + m.budgeted, 0),
    actual: months.reduce((sum, m) => sum + m.actual, 0),
  };
}

export function Overview() {
  const [rows, setRows] = useState<ReportRow[]>([]);
  const [topLevelIds, setTopLevelIds] = useState<Set<number>>(new Set());
  const [uncategorizedCount, setUncategorizedCount] = useState(0);

  useEffect(() => {
    const now = new Date();
    overviewApi.get(now.getFullYear(), now.getMonth() + 1).then(setRows);
    transactionsApi.uncategorizedCount().then((r) => setUncategorizedCount(r.count));
    categoriesApi.list().then((tree) => setTopLevelIds(new Set(tree.map((c) => c.id))));
  }, []);

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
              <tr key={row.category_id} style={row.is_parent ? { fontWeight: 600 } : undefined}>
                <td style={row.depth > 0 ? { paddingLeft: 26 * row.depth } : undefined}>{row.name}</td>
                <td className="right">{row.has_budget ? fmtMoney(budgeted) : "—"}</td>
                <td className="right">{fmtMoney(actual)}</td>
                <td className={"right" + (balance !== null && balance < 0 ? " neg" : "")}>
                  {balance !== null ? fmtMoney(balance) : "—"}
                </td>
              </tr>
            );
          })}
          <tr style={{ fontWeight: 700, borderTop: "2px solid var(--line-strong)" }}>
            <td>Grand total (expenses − income)</td>
            <td></td>
            <td></td>
            <td className={"right" + (grandTotal < 0 ? " neg" : "")}>{fmtMoney(grandTotal)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

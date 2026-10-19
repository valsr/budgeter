import { Fragment, useEffect, useState } from "react";
import { sharedBudgetsApi } from "../../api/sharedBudgets";
import type { SharedReportRow } from "../../api/types";
import { formatMoney } from "../../format";

import { CURRENT_YEAR, MONTH_LABELS, YEARS } from "./tree";

const CURRENT_MONTH = new Date().getMonth() + 1;

/** Same column tinting as the Budgets report: odd months light, the last one stronger. */
function monthClass(i: number, total: number): string {
  if (i === total - 1) return "month-current";
  return i % 2 === 1 ? "month-alt" : "";
}

/** The Budgets report layout, with each category expandable into one row per member. */
export function ReportTab({ budgetId }: { budgetId: number }) {
  const [year, setYear] = useState(CURRENT_YEAR);
  const [throughMonth, setThroughMonth] = useState(CURRENT_MONTH);
  const [rows, setRows] = useState<SharedReportRow[] | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    let stale = false;
    sharedBudgetsApi.report(budgetId, year, throughMonth).then(
      (r) => !stale && setRows(r),
      () => !stale && setRows([]), // the global error toast has already said why
    );
    return () => {
      stale = true;
    };
  }, [budgetId, year, throughMonth]);

  function toggle(key: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const months = Array.from({ length: throughMonth }, (_, i) => i + 1);

  return (
    <div>
      <div className="filters" style={{ marginBottom: 20, display: "flex", gap: 8, alignItems: "center" }}>
        <label htmlFor="shared-report-year">Year</label>
        <select id="shared-report-year" value={year} onChange={(e) => setYear(Number(e.target.value))}>
          {YEARS.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>
        <label htmlFor="shared-report-through">Through</label>
        <select
          id="shared-report-through"
          value={throughMonth}
          onChange={(e) => setThroughMonth(Number(e.target.value))}
        >
          {MONTH_LABELS.map((label, i) => (
            <option key={label} value={i + 1}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {rows !== null && rows.length === 0 ? (
        <p className="sub">No shared categories with figures for {year} yet — add some under Setup.</p>
      ) : (
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
            {(rows ?? []).map((row) => {
              const open = expanded.has(row.row_key);
              const indent = row.depth > 0 ? { paddingLeft: 22 * row.depth, color: "var(--ink-2)" } : undefined;
              return (
                <Fragment key={row.row_key}>
                  <tr style={row.is_parent ? { fontWeight: 600 } : undefined}>
                    <td style={indent}>
                      <button
                        type="button"
                        className="btn ghost sm"
                        style={{ padding: "0 5px", marginRight: 6 }}
                        aria-expanded={open}
                        aria-label={`${open ? "Hide" : "Show"} members of ${row.name}`}
                        onClick={() => toggle(row.row_key)}
                      >
                        {open ? "▾" : "▸"}
                      </button>
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
                  {open &&
                    row.members.map((member) => (
                      <tr key={`${row.row_key}:user:${member.user_id}`} className="breakdown-row">
                        <td style={{ paddingLeft: 28 + 22 * row.depth }}>
                          <span className="breakdown-mark">↳</span>
                          {member.username}
                        </td>
                        {months.map((m, i) => {
                          const actual = member.monthly[m] ?? 0;
                          const cls = monthClass(i, months.length);
                          return (
                            <Fragment key={m}>
                              <td className={cls} />
                              <td className={"right " + cls + (actual < 0 ? " neg" : "")}>{formatMoney(actual)}</td>
                            </Fragment>
                          );
                        })}
                        <td className={"right" + (member.ytd_actual < 0 ? " neg" : "")} title="Actual so far this year">
                          {formatMoney(member.ytd_actual)}
                        </td>
                      </tr>
                    ))}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

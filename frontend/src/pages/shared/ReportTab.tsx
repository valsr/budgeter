import { Fragment, useEffect, useState } from "react";
import { sharedBudgetsApi } from "../../api/sharedBudgets";
import type { SharedReportRow } from "../../api/types";
import { formatMoney } from "../../format";

import { MonthCells, ReportHead } from "../../components/ReportTable";
import { MONTH_LABELS, monthClass } from "../../components/reportColumns";
import { LoadError } from "./LoadError";
import { CURRENT_YEAR, YEARS } from "./tree";

const CURRENT_MONTH = new Date().getMonth() + 1;

/** The Budgets report layout, with each category expandable into one row per member. */
export function ReportTab({ budgetId }: { budgetId: number }) {
  const [year, setYear] = useState(CURRENT_YEAR);
  const [throughMonth, setThroughMonth] = useState(CURRENT_MONTH);
  const [rows, setRows] = useState<SharedReportRow[] | null>(null);
  const [failed, setFailed] = useState(false);
  // Bumped by Retry to run the load again with the same year and month.
  const [attempt, setAttempt] = useState(0);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    let stale = false;
    setRows(null);
    setFailed(false);
    sharedBudgetsApi.report(budgetId, year, throughMonth).then(
      (r) => !stale && setRows(r),
      () => !stale && setFailed(true),
    );
    return () => {
      stale = true;
    };
  }, [budgetId, year, throughMonth, attempt]);

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

      {failed ? (
        <LoadError message={`Couldn't load the report for ${year}.`} onRetry={() => setAttempt((n) => n + 1)} />
      ) : rows !== null && rows.length === 0 ? (
        <p className="sub">No shared categories with figures for {year} yet — add some under Setup.</p>
      ) : (
        <table id="budget-report-table">
          <ReportHead months={months} />
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
                    {months.map((m, i) => (
                      <MonthCells
                        key={m}
                        cell={row.monthly[m] ?? { budgeted: 0, actual: 0 }}
                        className={monthClass(i, months.length)}
                      />
                    ))}
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

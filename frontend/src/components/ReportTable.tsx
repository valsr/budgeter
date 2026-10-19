import { Fragment } from "react";
import type { ReactNode } from "react";
import type { MonthCell } from "../api/types";
import { formatMoney } from "../format";
import { MONTH_LABELS, monthClass } from "./reportColumns";

/** The budget report's two-row header: a Budgeted/Actual pair per month, then the YTD diff. Shared
 * by the Budgets report and the shared budget report so they stay alike. */
export function ReportHead({ months }: { months: number[] }) {
  return (
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
  );
}

/** One month's Budgeted and Actual cells. `className` carries the month tint (plus any extras);
 * `budgeted`/`actual` replace the plain formatted figures, e.g. with a split bubble. */
export function MonthCells({
  cell,
  className,
  budgeted,
  actual,
}: {
  cell: MonthCell;
  className: string;
  budgeted?: ReactNode;
  actual?: ReactNode;
}) {
  const over = cell.actual > cell.budgeted;
  return (
    <>
      <td className={"right muted-cell " + className + (cell.budgeted < 0 ? " neg" : "")}>
        {budgeted ?? formatMoney(cell.budgeted)}
      </td>
      <td className={"right " + className + (over ? " over" : cell.actual < 0 ? " neg" : "")}>
        {actual ?? formatMoney(cell.actual)}
      </td>
    </>
  );
}

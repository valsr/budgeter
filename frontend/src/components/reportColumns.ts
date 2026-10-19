export const MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Wireframe's monthClass(): odd columns get a light tint, the last (current)
 * month gets a stronger one — matches docs/wireframes.html's renderBudgetReport. */
export function monthClass(i: number, total: number): string {
  if (i === total - 1) return "month-current";
  return i % 2 === 1 ? "month-alt" : "";
}

/** Shared money formatting for report/overview screens: always `$`-prefixed,
 * `'` as the thousands separator (not `,`), and no leading `+` for positive
 * values -- a plain number already reads as positive without one. */
export function formatMoney(n: number, decimals = 2): string {
  const sign = n < 0 ? "-" : "";
  const [whole, frac] = Math.abs(n).toFixed(decimals).split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, "'");
  return `${sign}$${grouped}${frac ? "." + frac : ""}`;
}

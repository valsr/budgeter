/** Shared money formatting for report/overview screens: always `$`-prefixed,
 * `'` as the thousands separator (not `,`), no leading `+` for positive
 * values, and no leading `-` for negative ones either -- callers are
 * expected to signal negative amounts with color (see the `neg`/`diff-neg`/
 * `over` CSS classes) instead of a sign character. */
export function formatMoney(n: number, decimals = 2): string {
  const [whole, frac] = Math.abs(n).toFixed(decimals).split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, "'");
  return `$${grouped}${frac ? "." + frac : ""}`;
}

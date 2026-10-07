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

/** `YYYY-MM-DD HH:MM:SS` in the browser's local time. The API serializes
 * its UTC timestamps without an offset (SQLite hands them back naive), so a
 * string with no zone designator is read as UTC rather than as local time. */
export function formatTimestamp(iso: string): string {
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(iso);
  const d = new Date(hasZone ? iso : iso + "Z");
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  );
}

/** Shared money formatting for report/overview screens: always `$`-prefixed, `'` as the thousands
 * separator (not `,`), no leading `+` for positive values, and no leading `-` for negative ones
 * either -- callers are expected to signal negative amounts with color (see the `neg`/`diff-neg`/
 * `over` CSS classes) instead of a sign character. */
export function formatMoney(n: number, decimals = 2): string {
  const [whole, frac] = Math.abs(n).toFixed(decimals).split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, "'");
  return `$${grouped}${frac ? "." + frac : ""}`;
}

/** `YYYY-MM-DD HH:MM:SS` in the browser's local time. */
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

/** "1d 2h 3m" — the two or three largest units, no seconds once past a minute. */
export function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h ${minutes}m`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m`;
  return `${s}s`;
}

/** "1.5 MB" — binary units, one decimal from KB up. */
export function formatBytes(bytes: number): string {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return unit === 0 ? `${value} B` : `${value.toFixed(1)} ${units[unit]}`;
}

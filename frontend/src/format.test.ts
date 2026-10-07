import { describe, expect, it } from "vitest";
import { formatTimestamp } from "./format";

function localParts(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  );
}

describe("formatTimestamp", () => {
  it("renders YYYY-MM-DD HH:MM:SS in local time", () => {
    expect(formatTimestamp("2026-07-29T00:53:46Z")).toBe(localParts(new Date(Date.UTC(2026, 6, 29, 0, 53, 46))));
    expect(formatTimestamp("2026-07-29T00:53:46Z")).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/);
  });

  it("reads an offset-less API timestamp as UTC, not local time", () => {
    expect(formatTimestamp("2026-07-29T00:53:46.341078")).toBe(formatTimestamp("2026-07-29T00:53:46Z"));
  });

  it("honours an explicit offset", () => {
    expect(formatTimestamp("2026-07-29T02:53:46+02:00")).toBe(formatTimestamp("2026-07-29T00:53:46Z"));
  });

  it("returns unparseable input unchanged", () => {
    expect(formatTimestamp("not a date")).toBe("not a date");
  });
});

import { describe, expect, it } from "vitest";
import { buildQuery } from "./history";

describe("buildQuery", () => {
  it("defaults to page 1 and page_size 50 with no filters", () => {
    const params = new URLSearchParams(buildQuery({}));
    expect(params.get("page")).toBe("1");
    expect(params.get("page_size")).toBe("50");
    expect(params.has("entity_type")).toBe(false);
    expect(params.has("date_from")).toBe(false);
    expect(params.has("date_to")).toBe(false);
  });

  it("includes entity_type and date range when provided", () => {
    const params = new URLSearchParams(
      buildQuery({ entityType: "account", dateFrom: "2026-01-01", dateTo: "2026-01-31" }),
    );
    expect(params.get("entity_type")).toBe("account");
    expect(params.get("date_from")).toBe("2026-01-01");
    expect(params.get("date_to")).toBe("2026-01-31");
  });

  it("uses the given page and pageSize", () => {
    const params = new URLSearchParams(buildQuery({ page: 3, pageSize: 20 }));
    expect(params.get("page")).toBe("3");
    expect(params.get("page_size")).toBe("20");
  });
});

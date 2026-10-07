import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { formatTimestamp } from "../format";
import { History } from "./History";

vi.mock("../api/history", () => ({
  historyApi: {
    list: () =>
      Promise.resolve({
        items: [
          {
            group_id: "g1",
            entity_type: "account",
            operation: "create",
            summary: "Created account Checking",
            // What the API actually sends: UTC with no zone designator.
            created_at: "2026-07-29T00:53:46.341078",
            undone_at: null,
            is_stale: false,
            items: [],
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
      }),
    undo: vi.fn(),
  },
}));

it("shows when a change happened in local time, reading the API's timestamp as UTC", async () => {
  const expected = formatTimestamp("2026-07-29T00:53:46Z");
  expect(expected).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/);
  render(<History />);
  expect(await screen.findByText(expected)).toBeInTheDocument();
});

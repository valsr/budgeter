import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { Budget, ReportRow } from "../api/types";
import { Budgets } from "./Budgets";

const listBudgets = vi.fn();
const report = vi.fn();
const overview = vi.fn();
vi.mock("../api/budgets", () => ({
  budgetsApi: {
    list: () => listBudgets(),
    report: (...args: unknown[]) => report(...args),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    get: vi.fn(),
  },
  overviewApi: { get: (...args: unknown[]) => overview(...args) },
}));
vi.mock("../api/categories", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/categories")>()),
  categoriesApi: { list: vi.fn().mockResolvedValue([]) },
}));

const budget: Budget = {
  id: 1,
  name: "Household",
  budget_categories: [],
  dropped_categories: [],
};

function row(category_id: number, name: string): ReportRow {
  return {
    category_id,
    name,
    is_parent: false,
    monthly: { 1: { budgeted: 100, actual: 19.95 } },
    ytd_diff: 80.05,
    has_budget: true,
    depth: 0,
    is_income: false,
  };
}

const ROWS = [row(1, "groceries"), row(2, "utilities")];

beforeEach(() => {
  listBudgets.mockReset().mockResolvedValue([budget]);
  report.mockReset().mockResolvedValue(ROWS);
  overview.mockReset().mockResolvedValue([]);
});

function rowFor(name: string) {
  return screen.getByText(name).closest("tr")!;
}

it("highlights the row that was clicked", async () => {
  render(<Budgets />);
  await screen.findByText("groceries");

  expect(rowFor("groceries").className).not.toMatch(/row-highlight/);
  fireEvent.click(rowFor("groceries"));
  expect(rowFor("groceries").className).toMatch(/row-highlight/);
});

it("moves the highlight to a different row rather than adding a second", async () => {
  render(<Budgets />);
  await screen.findByText("groceries");

  fireEvent.click(rowFor("groceries"));
  fireEvent.click(rowFor("utilities"));

  expect(rowFor("utilities").className).toMatch(/row-highlight/);
  expect(rowFor("groceries").className).not.toMatch(/row-highlight/);
});

it("keeps the highlight when the same row is clicked again", async () => {
  render(<Budgets />);
  await screen.findByText("groceries");

  fireEvent.click(rowFor("groceries"));
  fireEvent.click(rowFor("groceries"));

  // A stray second click while reading figures across must not wipe the mark.
  expect(rowFor("groceries").className).toMatch(/row-highlight/);
});

it("clears the highlight on Escape", async () => {
  render(<Budgets />);
  await screen.findByText("groceries");

  fireEvent.click(rowFor("groceries"));
  fireEvent.keyDown(window, { key: "Escape" });

  await waitFor(() => expect(rowFor("groceries").className).not.toMatch(/row-highlight/));
});

it("shows cents rather than rounding to the nearest dollar", async () => {
  render(<Budgets />);
  await screen.findByText("groceries");

  const cells = Array.from(rowFor("groceries").querySelectorAll("td")).map((c) => c.textContent);
  expect(cells).toContain("$19.95");
  expect(cells).not.toContain("$20");
  expect(cells).toContain("$100.00");
  expect(cells).toContain("$80.05");
});

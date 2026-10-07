import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import type { Budget, ReportRow } from "../api/types";
import { TestAuth } from "../test/TestAuth";
import { Overview } from "./Overview";

const listBudgets = vi.fn();
const report = vi.fn();
const overview = vi.fn();
vi.mock("../api/budgets", () => ({
  budgetsApi: {
    list: () => listBudgets(),
    report: (...args: unknown[]) => report(...args),
  },
  overviewApi: { get: (...args: unknown[]) => overview(...args) },
}));
vi.mock("../api/categories", () => ({
  categoriesApi: { list: () => Promise.resolve([{ id: 1 }, { id: 2 }]) },
}));
vi.mock("../api/transactions", () => ({
  transactionsApi: { uncategorizedCount: () => Promise.resolve({ count: 0 }) },
}));

const STORAGE_KEY = "budgeter.u1.overview.budget";

function row(category_id: number, name: string, budgeted: number, actual: number): ReportRow {
  return {
    row_key: `cat:${category_id}`,
    category_id,
    account_id: null,
    name,
    is_parent: false,
    monthly: { 1: { budgeted, actual } },
    ytd_diff: budgeted - actual,
    has_budget: true,
    depth: 0,
    is_income: false,
  };
}

const BUDGETS: Budget[] = [
  { id: 1, name: "Household", budget_categories: [], dropped_categories: [] },
  { id: 2, name: "Travel", budget_categories: [], dropped_categories: [] },
];

function renderOverview() {
  return render(
    <MemoryRouter>
      <TestAuth>
        <Overview />
      </TestAuth>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  localStorage.clear();
  listBudgets.mockReset().mockResolvedValue(BUDGETS);
  overview.mockReset().mockResolvedValue([row(1, "everything", 0, 10)]);
  report.mockReset().mockImplementation((id: number) =>
    Promise.resolve(id === 1 ? [row(1, "groceries", 100, 40)] : [row(2, "flights", 900, 300)]),
  );
});

it("defaults to the first budget and shows its report", async () => {
  renderOverview();
  expect(await screen.findByText("groceries")).toBeInTheDocument();
  expect(screen.getByLabelText("Budget")).toHaveValue("1");
  const now = new Date();
  expect(report).toHaveBeenCalledWith(1, now.getFullYear(), now.getMonth() + 1);
  expect(overview).not.toHaveBeenCalled();
});

it("switches budgets and remembers the choice", async () => {
  renderOverview();
  await screen.findByText("groceries");

  fireEvent.change(screen.getByLabelText("Budget"), { target: { value: "2" } });

  expect(await screen.findByText("flights")).toBeInTheDocument();
  expect(screen.queryByText("groceries")).not.toBeInTheDocument();
  expect(localStorage.getItem(STORAGE_KEY)).toBe("2");
});

it("restores the last selected budget", async () => {
  localStorage.setItem(STORAGE_KEY, "2");
  renderOverview();
  expect(await screen.findByText("flights")).toBeInTheDocument();
  expect(screen.getByLabelText("Budget")).toHaveValue("2");
  expect(report).toHaveBeenCalledTimes(1);
});

it("offers and remembers the all-categories view", async () => {
  renderOverview();
  await screen.findByText("groceries");

  fireEvent.change(screen.getByLabelText("Budget"), { target: { value: "all" } });
  expect(await screen.findByText("everything")).toBeInTheDocument();
  expect(localStorage.getItem(STORAGE_KEY)).toBe("all");
});

it("restores a remembered all-categories choice even when budgets exist", async () => {
  localStorage.setItem(STORAGE_KEY, "all");
  renderOverview();
  expect(await screen.findByText("everything")).toBeInTheDocument();
  expect(report).not.toHaveBeenCalled();
});

it("falls back to the first budget when the remembered one is gone", async () => {
  localStorage.setItem(STORAGE_KEY, "99");
  renderOverview();
  expect(await screen.findByText("groceries")).toBeInTheDocument();
  expect(screen.getByLabelText("Budget")).toHaveValue("1");
});

it("shows all categories when no budgets exist", async () => {
  listBudgets.mockResolvedValue([]);
  renderOverview();
  expect(await screen.findByText("everything")).toBeInTheDocument();
  expect(screen.getByLabelText("Budget")).toHaveValue("all");
});

it("leaves per-account breakdown rows out of the summary", async () => {
  report.mockResolvedValue([
    row(1, "groceries", 100, 40),
    { ...row(1, "Visa", 60, 30), row_key: "cat:1:acct:8", account_id: 8, depth: 1 },
  ]);
  renderOverview();
  await screen.findByText("groceries");
  await waitFor(() => expect(screen.queryByText("Visa")).not.toBeInTheDocument());
});

it("does not pick up another user's remembered budget", async () => {
  localStorage.setItem("budgeter.u2.overview.budget", "2");
  renderOverview();
  expect(await screen.findByText("groceries")).toBeInTheDocument();
  expect(screen.getByLabelText("Budget")).toHaveValue("1");
});

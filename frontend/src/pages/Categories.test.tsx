import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { Category } from "../api/types";
import { TestAuth } from "../test/TestAuth";
import { Categories } from "./Categories";

vi.mock("../api/accounts", () => ({
  accountsApi: { list: () => Promise.resolve([]) },
}));
const TREE: Category[] = [
  {
    id: 1,
    name: "shared",
    parent_id: null,
    color: "#111",
    sort_order: 0,
    archived_at: null,
    is_income: false,
    children: [
      { id: 2, name: "groceries", parent_id: 1, color: "#222", sort_order: 0, archived_at: null, is_income: false, children: [] },
    ],
  },
];
vi.mock("../api/categories", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/categories")>()),
  categoriesApi: { list: () => Promise.resolve(TREE) },
}));

const tableProps = vi.fn();
vi.mock("../components/TransactionTable", () => ({
  TransactionTable: (props: { lockCategoryId?: number }) => {
    tableProps(props);
    return <div data-testid="txn-table">category {props.lockCategoryId}</div>;
  },
}));

const STORAGE_KEY = "budgeter.u1.categories.selected";

const page = (
  <TestAuth>
    <Categories />
  </TestAuth>
);

beforeEach(() => {
  localStorage.clear();
  tableProps.mockReset();
});

it("shows no transactions until a category is picked", async () => {
  render(page);
  expect(await screen.findByText(/Pick a category/)).toBeInTheDocument();
  expect(screen.queryByTestId("txn-table")).not.toBeInTheDocument();
});

it("locks the transaction list to the picked category and remembers it", async () => {
  render(page);
  const input = await screen.findByPlaceholderText("Choose a category…");
  fireEvent.focus(input);
  fireEvent.change(input, { target: { value: "groceries" } });
  fireEvent.mouseDown(await screen.findByText("shared:groceries"));

  expect(await screen.findByTestId("txn-table")).toHaveTextContent("category 2");
  expect(localStorage.getItem(STORAGE_KEY)).toBe("2");
});

it("restores the last picked category, parents included", async () => {
  localStorage.setItem(STORAGE_KEY, "1");
  render(page);
  expect(await screen.findByTestId("txn-table")).toHaveTextContent("category 1");
});

it("ignores a remembered category that no longer exists", async () => {
  localStorage.setItem(STORAGE_KEY, "99");
  render(page);
  expect(await screen.findByText(/Pick a category/)).toBeInTheDocument();
  expect(screen.queryByTestId("txn-table")).not.toBeInTheDocument();
});

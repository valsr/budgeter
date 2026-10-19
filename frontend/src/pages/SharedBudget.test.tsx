import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import type { Category, SharedBudget, SharedCategory, SharedReportRow } from "../api/types";
import { TestAuth } from "../test/TestAuth";
import { SharedBudget as SharedBudgetPage } from "./SharedBudget";

const api = {
  get: vi.fn(),
  rename: vi.fn(),
  remove: vi.fn(),
  setMembers: vi.fn(),
  categories: vi.fn(),
  createCategory: vi.fn(),
  updateCategory: vi.fn(),
  deleteCategory: vi.fn(),
  amounts: vi.fn(),
  setAmounts: vi.fn(),
  links: vi.fn(),
  setLinks: vi.fn(),
  report: vi.fn(),
  directory: vi.fn(),
};
vi.mock("../api/sharedBudgets", () => ({
  sharedBudgetsApi: new Proxy(
    {},
    { get: (_t, key: string) => (...args: unknown[]) => api[key as keyof typeof api](...args) },
  ),
}));
const listCategories = vi.fn();
vi.mock("../api/categories", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/categories")>()),
  categoriesApi: { list: (...args: unknown[]) => listCategories(...args) },
}));

const now = new Date();
const YEAR = now.getFullYear();
const MONTH = now.getMonth() + 1;

const HOUSEHOLD: SharedBudget = {
  id: 1,
  name: "Household",
  members: [
    { user_id: 1, username: "alice", is_disabled: false },
    { user_id: 2, username: "bob", is_disabled: false },
  ],
};

function shared(id: number, name: string, extra: Partial<SharedCategory> = {}): SharedCategory {
  return { id, name, parent_id: null, sort_order: 0, is_income: false, archived: false, ...extra };
}

function own(id: number, name: string, children: Category[] = []): Category {
  return {
    id,
    name,
    parent_id: null,
    color: "#111",
    sort_order: 0,
    archived_at: null,
    is_income: false,
    children: children.map((c) => ({ ...c, parent_id: id })),
  };
}

beforeEach(() => {
  for (const fn of Object.values(api)) fn.mockReset().mockResolvedValue([]);
  api.get.mockResolvedValue(HOUSEHOLD);
  api.directory.mockResolvedValue([
    { id: 1, username: "alice" },
    { id: 2, username: "bob" },
    { id: 3, username: "carol" },
  ]);
  listCategories.mockReset().mockResolvedValue([]);
});

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/shared-budgets/1"]}>
      <TestAuth>
        <Routes>
          <Route path="/shared-budgets" element={<p>Shared budgets list</p>} />
          <Route path="/shared-budgets/:id" element={<SharedBudgetPage />} />
        </Routes>
      </TestAuth>
    </MemoryRouter>,
  );
}

async function openTab(name: string) {
  renderPage();
  await screen.findByRole("heading", { name: "Household" });
  fireEvent.click(screen.getByRole("button", { name }));
}

it("shows a not-found state when the budget can't be loaded", async () => {
  api.get.mockRejectedValue(new ApiError(404, "Not found"));
  renderPage();
  expect(await screen.findByText(/shared budget not found/i)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /back to shared budgets/i })).toHaveAttribute("href", "/shared-budgets");
});

it("report expands a category into one row per member", async () => {
  const row: SharedReportRow = {
    row_key: "cat:5",
    category_id: 5,
    account_id: null,
    name: "Groceries",
    is_parent: false,
    monthly: { [MONTH]: { budgeted: 300, actual: 120 } },
    ytd_diff: 180,
    has_budget: true,
    depth: 0,
    is_income: false,
    members: [
      { user_id: 1, username: "alice", monthly: { [MONTH]: 70 }, ytd_actual: 71.5 },
      { user_id: 2, username: "bob", monthly: { [MONTH]: 50 }, ytd_actual: 52.25 },
    ],
  };
  api.report.mockResolvedValue([row]);
  renderPage();

  expect(await screen.findByText("Groceries")).toBeInTheDocument();
  expect(api.report).toHaveBeenCalledWith(1, YEAR, MONTH);
  expect(screen.queryByText("alice")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Show members of Groceries" }));
  const aliceRow = screen.getByText("alice").closest("tr")!;
  expect(aliceRow).toHaveClass("breakdown-row");
  expect(within(aliceRow).getByText("$70.00")).toBeInTheDocument();
  expect(within(aliceRow).getByText("$71.50")).toBeInTheDocument();
  expect(within(screen.getByText("bob").closest("tr")!).getByText("$52.25")).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Year"), { target: { value: String(YEAR - 1) } });
  await waitFor(() => expect(api.report).toHaveBeenLastCalledWith(1, YEAR - 1, MONTH));
  fireEvent.change(screen.getByLabelText("Through"), { target: { value: "12" } });
  await waitFor(() => expect(api.report).toHaveBeenLastCalledWith(1, YEAR - 1, 12));
});

it("mappings hide a category mapped elsewhere and save the whole list", async () => {
  api.categories.mockResolvedValue([
    shared(1, "Home"),
    shared(2, "Leisure"),
    shared(3, "Old stuff", { archived: true }),
  ]);
  api.links.mockResolvedValue([{ category_id: 11, shared_category_id: 1 }]);
  listCategories.mockResolvedValue([own(10, "Food", [own(11, "Groceries"), own(12, "Dining")]), own(20, "Fun")]);
  await openTab("My mappings");

  const homeRow = (await screen.findByText("Food:Groceries")).closest("tr")!;
  expect(within(homeRow).getByText("Home")).toBeInTheDocument();
  expect(screen.queryByText("Old stuff")).not.toBeInTheDocument();

  const leisureRow = screen.getByText("Leisure").closest("tr")!;
  fireEvent.focus(within(leisureRow).getByRole("textbox"));
  const menu = leisureRow.querySelector(".cat-combobox-menu") as HTMLElement;
  expect(within(menu).queryByText("Food:Groceries")).not.toBeInTheDocument();
  expect(within(menu).getByText("Food:Dining")).toBeInTheDocument();
  // Parents are mappable too.
  expect(within(menu).getByText("Food")).toBeInTheDocument();
  fireEvent.mouseDown(within(menu).getByText("Fun"));
  expect(within(leisureRow).getByText("Fun")).toBeInTheDocument();

  api.setLinks.mockResolvedValue([]);
  fireEvent.click(screen.getByRole("button", { name: "Save mappings" }));
  await waitFor(() =>
    expect(api.setLinks).toHaveBeenCalledWith(1, [
      { category_id: 11, shared_category_id: 1 },
      { category_id: 20, shared_category_id: 2 },
    ]),
  );
});

it("setup saves amounts for the year, sending blanks as null", async () => {
  api.categories.mockResolvedValue([shared(1, "Home")]);
  api.amounts.mockResolvedValue([
    { shared_category_id: 1, month: 1, amount: 100 },
    { shared_category_id: 1, month: 2, amount: 50 },
  ]);
  await openTab("Setup");

  const feb = await screen.findByLabelText("Home Feb");
  await waitFor(() => expect(feb).toHaveValue("50"));
  expect(api.amounts).toHaveBeenCalledWith(1, YEAR);
  fireEvent.change(feb, { target: { value: "" } });
  fireEvent.change(screen.getByLabelText("Home Mar"), { target: { value: "25.5" } });
  fireEvent.click(screen.getByRole("button", { name: "Save amounts" }));

  await waitFor(() => expect(api.setAmounts).toHaveBeenCalled());
  const [id, year, lines] = api.setAmounts.mock.calls[0];
  expect(id).toBe(1);
  expect(year).toBe(YEAR);
  expect(lines).toHaveLength(12);
  expect(lines).toContainEqual({ shared_category_id: 1, month: 1, amount: 100 });
  expect(lines).toContainEqual({ shared_category_id: 1, month: 2, amount: null });
  expect(lines).toContainEqual({ shared_category_id: 1, month: 3, amount: 25.5 });
  expect(lines).toContainEqual({ shared_category_id: 1, month: 4, amount: null });
});

it("setup offers only non-members to add", async () => {
  await openTab("Setup");
  const picker = await screen.findByLabelText("Add member");
  await waitFor(() => expect(within(picker).getByRole("option", { name: "carol" })).toBeInTheDocument());
  expect(within(picker).queryByRole("option", { name: "bob" })).not.toBeInTheDocument();
  fireEvent.change(picker, { target: { value: "3" } });
  fireEvent.click(screen.getByRole("button", { name: "Add" }));
  api.setMembers.mockResolvedValue({ ...HOUSEHOLD, members: [...HOUSEHOLD.members, { user_id: 3, username: "carol", is_disabled: false }] });
  fireEvent.click(screen.getByRole("button", { name: "Save members" }));
  await waitFor(() => expect(api.setMembers).toHaveBeenCalledWith(1, [1, 2, 3]));
});

it("removing yourself from the members navigates back to the list", async () => {
  api.setMembers.mockResolvedValue({ ...HOUSEHOLD, members: [HOUSEHOLD.members[1]] });
  await openTab("Setup");
  fireEvent.click(await screen.findByRole("button", { name: "Remove alice" }));
  fireEvent.click(screen.getByRole("button", { name: "Save members" }));
  await waitFor(() => expect(api.setMembers).toHaveBeenCalledWith(1, [2]));
  expect(await screen.findByText("Shared budgets list")).toBeInTheDocument();
});

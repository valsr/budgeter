import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { Account, Budget, Category, ReportRow } from "../api/types";
import { Budgets } from "./Budgets";

const listBudgets = vi.fn();
const createBudget = vi.fn();
const update = vi.fn();
const report = vi.fn();
const overview = vi.fn();
vi.mock("../api/budgets", () => ({
  budgetsApi: {
    list: () => listBudgets(),
    report: (...args: unknown[]) => report(...args),
    create: (...args: unknown[]) => createBudget(...args),
    update: (...args: unknown[]) => update(...args),
    remove: vi.fn(),
    get: vi.fn(),
  },
  overviewApi: { get: (...args: unknown[]) => overview(...args) },
}));
const listAccounts = vi.fn();
vi.mock("../api/accounts", () => ({
  accountsApi: { list: () => listAccounts() },
}));
const listCategories = vi.fn();
vi.mock("../api/categories", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/categories")>()),
  categoriesApi: { list: () => listCategories() },
}));

const ACCOUNTS: Account[] = [
  { id: 7, name: "Main", account_number: null, type: "asset", opening_balance: 0, color: "#111", balance: 0 },
  { id: 8, name: "Visa", account_number: null, type: "liability", opening_balance: 0, color: "#222", balance: 0 },
];

const CATEGORY_TREE: Category[] = [
  {
    id: 1,
    name: "groceries",
    parent_id: null,
    color: "#111",
    sort_order: 0,
    archived_at: null,
    is_income: false,
    children: [],
  },
];

const budget: Budget = {
  id: 1,
  name: "Household",
  budget_categories: [],
  dropped_categories: [],
};

function accountRow(
  category_id: number,
  account_id: number,
  name: string,
  cell: { budgeted: number; actual: number } = { budgeted: 0, actual: 0 },
  ytd: number | null = null,
): ReportRow {
  return {
    ...row(category_id, name),
    row_key: `cat:${category_id}:acct:${account_id}`,
    account_id,
    monthly: { 1: cell },
    has_budget: ytd !== null,
    ytd_diff: ytd ?? 0,
    depth: 1,
  };
}

function row(category_id: number, name: string): ReportRow {
  return {
    row_key: `cat:${category_id}`,
    category_id,
    account_id: null,
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
  listAccounts.mockReset().mockResolvedValue(ACCOUNTS);
  createBudget.mockReset().mockResolvedValue({ ...budget, dropped_categories: [] });
  update.mockReset().mockResolvedValue({ ...budget, dropped_categories: [] });
  listCategories.mockReset().mockResolvedValue(CATEGORY_TREE);
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

async function renderWithBreakdown() {
  report.mockResolvedValue([
    row(1, "groceries"),
    accountRow(1, 7, "Main", { budgeted: 60, actual: 10 }, 50),
    accountRow(1, 8, "Visa", { budgeted: 40, actual: 9.95 }, 30.05),
    row(2, "utilities"),
  ]);
  render(<Budgets />);
  await screen.findByText("groceries");
}

/** The pills in the hover bubble of one of a row's cells, by column index
 * (0 = category, then Budgeted/Actual per month to date; -1 = YTD diff). */
function pills(rowName: string, column: number): string[] {
  const cells = rowFor(rowName).querySelectorAll("td");
  const cell = cells[column < 0 ? cells.length + column : column];
  const bubble = cell.querySelector('[role="tooltip"]');
  return bubble ? Array.from(bubble.querySelectorAll(".tag")).map((p) => p.textContent ?? "") : [];
}

// --- the editor's per-source breakdown ---------------------------------

async function openEditor() {
  render(<Budgets />);
  await screen.findByText("groceries");
  fireEvent.click(screen.getByText("Edit budget"));
  await screen.findByText("Edit budget", { selector: "h2" });
}

it("budgets a category as one total by default", async () => {
  await openEditor();
  fireEvent.click(screen.getByRole("checkbox"));

  const janInput = screen.getAllByRole("textbox").find((el) => el.className.includes("month-input"))!;
  fireEvent.change(janInput, { target: { value: "400" } });
  fireEvent.click(screen.getByText("Save changes"));

  await waitFor(() => expect(update).toHaveBeenCalled());
  const payload = update.mock.calls[0][1];
  expect(payload.categories).toHaveLength(1);
  expect(payload.categories[0].account_id).toBeNull();
  expect(payload.categories[0].monthly_amounts[1]).toBe(400);
});

it("splits a category into one line per account", async () => {
  await openEditor();
  fireEvent.click(screen.getByText("per account"));

  fireEvent.change(screen.getByLabelText("groceries Main Jan"), { target: { value: "250" } });
  fireEvent.change(screen.getByLabelText("groceries Visa Jan"), { target: { value: "150" } });
  fireEvent.click(screen.getByText("Save changes"));

  await waitFor(() => expect(update).toHaveBeenCalled());
  const lines = update.mock.calls[0][1].categories;
  expect(lines.map((l: { account_id: number }) => l.account_id)).toEqual([7, 8]);
  expect(lines[0].monthly_amounts[1]).toBe(250);
  expect(lines[1].monthly_amounts[1]).toBe(150);
});

it("omits a line for an account left blank", async () => {
  await openEditor();
  fireEvent.click(screen.getByText("per account"));
  fireEvent.change(screen.getByLabelText("groceries Main Jan"), { target: { value: "250" } });
  fireEvent.click(screen.getByText("Save changes"));

  await waitFor(() => expect(update).toHaveBeenCalled());
  const lines = update.mock.calls[0][1].categories;
  // Visa was never budgeted, so it gets no line rather than a line of zeros.
  expect(lines.map((l: { account_id: number }) => l.account_id)).toEqual([7]);
});

it("shows the category total as the sum of its account lines", async () => {
  await openEditor();
  fireEvent.click(screen.getByText("per account"));

  fireEvent.change(screen.getByLabelText("groceries Main Jan"), { target: { value: "250" } });
  fireEvent.change(screen.getByLabelText("groceries Visa Jan"), { target: { value: "150.50" } });

  // Derived, not separately editable.
  expect(screen.getByText("$400.50")).toBeInTheDocument();
});

it("keeps the category budgeted when broken down but left empty", async () => {
  await openEditor();
  fireEvent.click(screen.getByText("per account"));
  fireEvent.click(screen.getByText("Save changes"));

  await waitFor(() => expect(update).toHaveBeenCalled());
  const lines = update.mock.calls[0][1].categories;
  // Falls back to a category-level line rather than dropping the selection.
  expect(lines).toHaveLength(1);
  expect(lines[0].account_id).toBeNull();
});


// --- the per-account split, shown on hover ------------------------------

it("lists a category once, with no breakdown rows or expander", async () => {
  await renderWithBreakdown();

  expect(document.querySelectorAll("#budget-report-table tbody tr")).toHaveLength(2);
  expect(screen.queryByLabelText(/breakdown by account/)).toBeNull();
  expect(rowFor("groceries").querySelector("td")!.textContent).toBe("groceries");
});

it("puts the split in a bubble on each amount: one pill per account", async () => {
  await renderWithBreakdown();

  expect(pills("groceries", 1)).toEqual(["Main: $60.00", "Visa: $40.00"]); // Jan budgeted
  expect(pills("groceries", 2)).toEqual(["Main: $10.00", "Visa: $9.95"]); // Jan actual
  expect(pills("groceries", -1)).toEqual(["Main: $50.00", "Visa: $30.05"]); // YTD diff
  // The cell still reads as the category's own figure.
  const budgeted = rowFor("groceries").querySelectorAll("td")[1];
  expect(budgeted.querySelector(".split-value")!.textContent).toBe("$100.00");
  expect(budgeted.className).toMatch(/has-split/);
});

it("puts each pill on its own line, in the account's colour", async () => {
  await renderWithBreakdown();

  const bubble = rowFor("groceries").querySelectorAll("td")[1].querySelector('[role="tooltip"]')!;
  const [main, visa] = Array.from(bubble.children) as HTMLElement[];
  expect(bubble.children).toHaveLength(2);
  expect(main.className).toMatch(/split-line/);
  expect(main.querySelector(".tag")).toHaveStyle({ color: "#111" }); // Main's colour
  expect(visa.querySelector(".tag")).toHaveStyle({ color: "#222" });
});

it("shows a minus on a negative share, since the pill's colour is the account's", async () => {
  report.mockResolvedValue([
    row(1, "groceries"),
    accountRow(1, 7, "Main", { budgeted: 60, actual: -12.5 }),
    accountRow(1, 8, "Visa", { budgeted: 40, actual: 32.45 }),
  ]);
  render(<Budgets />);
  await screen.findByText("groceries");

  expect(pills("groceries", 2)).toEqual(["Main: -$12.50", "Visa: $32.45"]);
});

it("leaves the diff without a bubble when no account has a budget of its own", async () => {
  report.mockResolvedValue([row(1, "groceries"), accountRow(1, 7, "Main", { budgeted: 0, actual: 19.95 })]);
  render(<Budgets />);
  await screen.findByText("groceries");

  expect(pills("groceries", 2)).toEqual(["Main: $19.95"]);
  expect(pills("groceries", -1)).toEqual([]);
  const cells = Array.from(rowFor("groceries").querySelectorAll("td")).map((c) => c.textContent);
  expect(cells[cells.length - 1]).toBe("$80.05");
});

it("offers no bubble for a category with no breakdown", async () => {
  await renderWithBreakdown();

  expect(rowFor("utilities").querySelector('[role="tooltip"]')).toBeNull();
  expect(rowFor("utilities").querySelector(".has-split")).toBeNull();
  const cells = Array.from(rowFor("utilities").querySelectorAll("td")).map((c) => c.textContent);
  expect(cells).toContain("$19.95");
});

it("still highlights a category that has a split", async () => {
  await renderWithBreakdown();

  fireEvent.click(rowFor("groceries"));
  expect(rowFor("groceries").className).toMatch(/row-highlight/);
});


// --- filtering the report to a subset of accounts ----------------------

it("requests the report unfiltered by default", async () => {
  render(<Budgets />);
  await screen.findByText("groceries");

  await waitFor(() => expect(report).toHaveBeenCalled());
  expect(report.mock.calls[0]).toEqual([1, expect.any(Number), expect.any(Number), []]);
  expect(screen.getByText(/All accounts/)).toBeInTheDocument();
});

it("refetches immediately when an account is deselected", async () => {
  render(<Budgets />);
  await screen.findByText("groceries");
  report.mockClear();

  fireEvent.click(screen.getByText(/All accounts/));
  fireEvent.click(screen.getByLabelText("Visa"));

  // Live: no Apply step.
  await waitFor(() => expect(report).toHaveBeenCalled());
  expect(report.mock.calls[0][3]).toEqual([7]);
});

it("treats every account selected as no filter", async () => {
  render(<Budgets />);
  await screen.findByText("groceries");

  fireEvent.click(screen.getByText(/All accounts/));
  fireEvent.click(screen.getByLabelText("Visa"));
  await waitFor(() => expect(report.mock.calls.at(-1)?.[3]).toEqual([7]));
  report.mockClear();

  fireEvent.click(screen.getByLabelText("Visa"));
  await waitFor(() => expect(report.mock.calls.at(-1)?.[3]).toEqual([]));
});

it("says which accounts the figures cover while filtered", async () => {
  render(<Budgets />);
  await screen.findByText("groceries");

  fireEvent.click(screen.getByText(/All accounts/));
  fireEvent.click(screen.getByLabelText("Visa"));

  expect(await screen.findByText(/Main only/)).toBeInTheDocument();
});

it("closes the account menu on Escape", async () => {
  render(<Budgets />);
  await screen.findByText("groceries");

  fireEvent.click(screen.getByText(/All accounts/));
  expect(screen.getByLabelText("Visa")).toBeInTheDocument();

  fireEvent.keyDown(window, { key: "Escape" });
  await waitFor(() => expect(screen.queryByLabelText("Visa")).toBeNull());
});

it("will not let every account be unticked", async () => {
  render(<Budgets />);
  await screen.findByText("groceries");

  fireEvent.click(screen.getByText(/All accounts/));
  fireEvent.click(screen.getByLabelText("Visa"));
  await waitFor(() => expect(report.mock.calls.at(-1)?.[3]).toEqual([7]));
  report.mockClear();

  // A report over no accounts has nothing to show, so this is a no-op rather
  // than silently flipping back to "all".
  fireEvent.click(screen.getByLabelText("Main"));
  expect(report).not.toHaveBeenCalled();
  expect(screen.getByLabelText("Main")).toBeChecked();
});

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { Account, Transaction, TransactionPage } from "../api/types";
import { TransactionTable } from "./TransactionTable";
import { ToastProvider } from "./Toast";

const list = vi.fn();
const updateSplits = vi.fn();
vi.mock("../api/transactions", () => ({
  transactionsApi: {
    list: (...args: unknown[]) => list(...args),
    updateSplits: (...args: unknown[]) => updateSplits(...args),
    acceptSuggestion: vi.fn(),
    rejectSuggestion: vi.fn(),
    remove: vi.fn(),
    unlinkTransfer: vi.fn(),
    transferCandidates: vi.fn(),
    linkTransfer: vi.fn(),
  },
}));
vi.mock("../api/rules", () => ({
  rulesApi: { learnCheck: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), learn: vi.fn(), previewMatches: vi.fn() },
}));
vi.mock("../api/categories", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/categories")>()),
  categoriesApi: { list: vi.fn() },
}));

const accounts: Account[] = [
  { id: 1, name: "Main", account_number: null, type: "asset", opening_balance: 0, color: "#111", balance: 0 },
  { id: 2, name: "Home", account_number: null, type: "asset", opening_balance: 0, color: "#222", balance: 0 },
];

function txn(over: Partial<Transaction> & { id: number; account_id: number; amount: number }): Transaction {
  const { amount, ...rest } = over;
  return {
    date: "2026-01-19",
    name: "GEORGIEV RADOSL MSP",
    type: "normal",
    transfer_pair_id: null,
    splits: [{ id: over.id * 10, category_id: null, amount, suggested_category_id: null, suggestion_source: null }],
    ...rest,
  };
}

function page(items: Transaction[]): TransactionPage {
  return { items, total: items.length, page: 1, page_size: 100 };
}

function renderTable() {
  return render(
    <ToastProvider>
      <TransactionTable categories={[]} accounts={accounts} />
    </ToastProvider>,
  );
}

beforeEach(() => {
  list.mockReset();
  updateSplits.mockReset().mockResolvedValue(undefined);
});

const PAIR: Transaction[] = [
  txn({ id: 1, account_id: 1, amount: -1024, name: "PTS TO: 15096000884", type: "transfer", transfer_pair_id: 2 }),
  txn({ id: 2, account_id: 2, amount: 1024, name: "PTS FRM: 17366263382", type: "transfer", transfer_pair_id: 1 }),
];

it("shows a linked pair as one row with both accounts and a single amount", async () => {
  list.mockResolvedValue({ items: PAIR, total: 1, page: 1, page_size: 100 });
  renderTable();

  // The withdrawal leg names the row; the deposit leg is not a row of its own.
  await screen.findByText("PTS TO: 15096000884");
  expect(screen.queryByText("PTS FRM: 17366263382")).toBeNull();
  expect(screen.getAllByLabelText("Linked transfer")).toHaveLength(1);

  const row = screen.getByText("PTS TO: 15096000884").closest("tr")!;
  expect(row).toHaveTextContent("Main");
  expect(row).toHaveTextContent("Home");
  expect(row).toHaveTextContent("→");
  // One amount, not one per leg.
  expect(row.textContent?.match(/\$1024\.00/g)).toHaveLength(1);
});

it("names the hidden leg on the row it collapsed into", async () => {
  list.mockResolvedValue({ items: PAIR, total: 1, page: 1, page_size: 100 });
  renderTable();

  const nameCell = (await screen.findByText("PTS TO: 15096000884")).closest("td")!;
  expect(nameCell).toHaveAttribute("title", "Other leg: PTS FRM: 17366263382");
});

it("shows a pair's amount in the viewed account's own column", async () => {
  list.mockResolvedValue({ items: PAIR, total: 1, page: 1, page_size: 100 });
  render(
    <ToastProvider>
      <TransactionTable categories={[]} accounts={accounts} lockAccountId={2} />
    </ToastProvider>,
  );

  // Locked to Home, which received the money: it reads as a deposit there.
  const row = (await screen.findByText("PTS TO: 15096000884")).closest("tr")!;
  const cells = Array.from(row.querySelectorAll("td")).map((c) => c.textContent);
  expect(cells).toContain("$1024.00");
  expect(cells).toContain("—");
});

it("offers unlink but not split or link on a pair", async () => {
  list.mockResolvedValue({ items: PAIR, total: 1, page: 1, page_size: 100 });
  renderTable();

  await screen.findByText("PTS TO: 15096000884");
  expect(screen.getByTitle(/^Unlink transfer/)).toBeInTheDocument();
  expect(screen.queryByTitle(/^Link as transfer/)).toBeNull();
  expect(screen.queryByTitle("Split transaction")).toBeNull();
});

it("leaves an ordinary transaction as its own row", async () => {
  list.mockResolvedValue(page([txn({ id: 1, account_id: 1, amount: -20 })]));
  renderTable();

  await screen.findByText("GEORGIEV RADOSL MSP");
  expect(screen.queryByLabelText("Linked transfer")).toBeNull();
  expect(screen.getByTitle(/^Link as transfer/)).toBeInTheDocument();
});

it("keeps an orphan transfer leg as a plain row", async () => {
  list.mockResolvedValue(
    page([txn({ id: 1, account_id: 1, amount: -50, type: "transfer", transfer_pair_id: null })]),
  );
  renderTable();

  // No counterpart to collapse with, so it renders like any single row --
  // and can still be unlinked back to an ordinary transaction.
  await screen.findByText("GEORGIEV RADOSL MSP");
  expect(screen.queryByLabelText("Linked transfer")).toBeNull();
  expect(screen.getByTitle(/^Unlink transfer/)).toBeInTheDocument();
});

it("keeps a multi-split transaction on its own grouped rows", async () => {
  const split: Transaction = {
    id: 1,
    account_id: 1,
    date: "2026-01-19",
    name: "Costco",
    type: "normal",
    transfer_pair_id: null,
    splits: [
      { id: 10, category_id: null, amount: -60, suggested_category_id: null, suggestion_source: null },
      { id: 11, category_id: null, amount: -20, suggested_category_id: null, suggestion_source: null },
    ],
  };
  list.mockResolvedValue(page([split]));
  renderTable();

  await screen.findByText("Costco");
  await waitFor(() => expect(screen.getByText("↳ split")).toBeInTheDocument());
});

const CATEGORIES = [
  {
    id: 5,
    name: "contributions",
    parent_id: null,
    color: "#111",
    sort_order: 0,
    archived_at: null,
    is_income: false,
    children: [
      { id: 6, name: "rado", parent_id: 5, color: "#222", sort_order: 0, archived_at: null, is_income: false, children: [] },
    ],
  },
];

it("shows the pair's single category once, on the leg that carries it", async () => {
  // Linked from the deposit leg, so that leg holds the category.
  list.mockResolvedValue({
    items: [
      txn({ id: 1, account_id: 1, amount: -1024, name: "PTS TO", type: "transfer", transfer_pair_id: 2 }),
      {
        ...txn({ id: 2, account_id: 2, amount: 1024, name: "PTS FRM", type: "transfer", transfer_pair_id: 1 }),
        splits: [{ id: 20, category_id: 6, amount: 1024, suggested_category_id: null, suggestion_source: null }],
      },
    ],
    total: 1,
    page: 1,
    page_size: 100,
  });
  render(
    <ToastProvider>
      <TransactionTable categories={CATEGORIES} accounts={accounts} />
    </ToastProvider>,
  );

  await screen.findByText("PTS TO");
  expect(screen.getAllByText("contributions:rado")).toHaveLength(1);
});

it("writes a pair's category to the withdrawal leg when neither leg carries one", async () => {
  list.mockResolvedValue({ items: PAIR, total: 1, page: 1, page_size: 100 });
  render(
    <ToastProvider>
      <TransactionTable categories={CATEGORIES} accounts={accounts} />
    </ToastProvider>,
  );

  fireEvent.click(await screen.findByText("+ Assign category"));
  const input = await screen.findByPlaceholderText("Type to search or create…");
  fireEvent.focus(input);
  fireEvent.change(input, { target: { value: "rado" } });
  fireEvent.mouseDown(await screen.findByText("contributions:rado"));

  // Leg 1 is the −1024 withdrawal leg; the server clears the other.
  await waitFor(() => expect(updateSplits).toHaveBeenCalledWith(1, [{ category_id: 6, amount: -1024 }]));
});

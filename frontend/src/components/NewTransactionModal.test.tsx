import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Account, Category, Transaction } from "../api/types";
import { NewTransactionModal } from "./NewTransactionModal";
import { ToastProvider } from "./Toast";

const create = vi.fn();
vi.mock("../api/transactions", () => ({
  transactionsApi: {
    create: (...args: unknown[]) => create(...args),
  },
}));

const learnCheck = vi.fn();
vi.mock("../api/rules", () => ({
  rulesApi: {
    learnCheck: (...args: unknown[]) => learnCheck(...args),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    learn: vi.fn(),
    previewMatches: vi.fn(),
  },
}));
vi.mock("../api/categories", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/categories")>()),
  categoriesApi: { list: vi.fn() },
}));

function renderModal(props: Partial<Parameters<typeof NewTransactionModal>[0]> = {}) {
  return render(
    <ToastProvider>
      <NewTransactionModal accounts={accounts} categories={categories} onClose={() => {}} onSaved={() => {}} {...props} />
    </ToastProvider>,
  );
}

const accounts: Account[] = [
  { id: 1, name: "Checking", account_number: null, type: "asset", opening_balance: 0, color: "#4f8a9c", balance: 0 },
];

const categories: Category[] = [
  {
    id: 1,
    name: "personal",
    parent_id: null,
    color: "#111",
    sort_order: 0,
    archived_at: null, is_income: false,
    children: [{ id: 2, name: "dining", parent_id: 1, color: "#222", sort_order: 0, archived_at: null, is_income: false, children: [] }],
  },
];

const created: Transaction = {
  id: 42,
  account_id: 1,
  date: "2026-07-24",
  name: "Coffee",
  type: "normal",
  transfer_pair_id: null,
  splits: [{ id: 1, category_id: 2, amount: -4.5, suggested_category_id: null, suggestion_source: null }],
};

describe("NewTransactionModal", () => {
  beforeEach(() => {
    create.mockReset().mockResolvedValue(created);
    learnCheck.mockReset().mockResolvedValue({ status: "none", conflict: null, suggestion: null });
  });

  it("triggers the rule-learning check when a category is set", async () => {
    renderModal();
    fireEvent.change(screen.getByPlaceholderText("e.g. Trader Joe's"), { target: { value: "Coffee" } });
    fireEvent.change(screen.getByPlaceholderText("Amount"), { target: { value: "4.50" } });
    fireEvent.change(screen.getByDisplayValue("Unassigned"), { target: { value: "2" } });

    fireEvent.click(screen.getByText("Create transaction"));

    await vi.waitFor(() => expect(create).toHaveBeenCalled());
    await vi.waitFor(() => expect(learnCheck).toHaveBeenCalledWith(42));
  });

  it("does not trigger the rule-learning check when left unassigned", async () => {
    renderModal();
    fireEvent.change(screen.getByPlaceholderText("e.g. Trader Joe's"), { target: { value: "Coffee" } });
    fireEvent.change(screen.getByPlaceholderText("Amount"), { target: { value: "4.50" } });

    fireEvent.click(screen.getByText("Create transaction"));

    await vi.waitFor(() => expect(create).toHaveBeenCalled());
    expect(learnCheck).not.toHaveBeenCalled();
  });
});

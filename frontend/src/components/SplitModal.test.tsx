import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Category, Transaction } from "../api/types";
import { SplitModal } from "./SplitModal";
import { ToastProvider } from "./Toast";

const updateSplits = vi.fn();
vi.mock("../api/transactions", () => ({
  transactionsApi: {
    updateSplits: (...args: unknown[]) => updateSplits(...args),
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

function renderModal(props: Parameters<typeof SplitModal>[0]) {
  return render(
    <ToastProvider>
      <SplitModal {...props} />
    </ToastProvider>,
  );
}

const categories: Category[] = [
  {
    id: 1,
    name: "shared",
    parent_id: null,
    color: "#111",
    sort_order: 0,
    archived_at: null, is_income: false,
    children: [
      { id: 2, name: "groceries", parent_id: 1, color: "#222", sort_order: 0, archived_at: null, is_income: false, children: [] },
      { id: 3, name: "household", parent_id: 1, color: "#333", sort_order: 1, archived_at: null, is_income: false, children: [] },
    ],
  },
];

const transaction: Transaction = {
  id: 10,
  account_id: 1,
  date: "2026-07-19",
  name: "Costco",
  type: "normal",
  transfer_pair_id: null,
  splits: [{ id: 100, category_id: 2, amount: -88.4, suggested_category_id: null, suggestion_source: null }],
};

const deposit: Transaction = {
  ...transaction,
  id: 11,
  name: "Paycheque",
  splits: [{ id: 101, category_id: 2, amount: 500, suggested_category_id: null, suggestion_source: null }],
};

const withdraws = () => screen.getAllByLabelText("Withdraw") as HTMLInputElement[];
const deposits = () => screen.getAllByLabelText("Deposit") as HTMLInputElement[];

function pickHousehold(rowIndex: number) {
  const categoryInputs = screen.getAllByDisplayValue("shared:groceries");
  fireEvent.focus(categoryInputs[rowIndex]);
  fireEvent.change(categoryInputs[rowIndex], { target: { value: "household" } });
  fireEvent.mouseDown(screen.getByText("shared:household"));
}

describe("SplitModal", () => {
  beforeEach(() => {
    updateSplits.mockReset();
    learnCheck.mockReset().mockResolvedValue({ status: "none", conflict: null, suggestion: null });
  });

  it("shows a withdrawal as a positive number in the Withdraw column", () => {
    renderModal({ transaction, categories, onClose: () => {}, onSaved: () => {} });
    expect(withdraws()[0].value).toBe("88.40");
    expect(deposits()[0].value).toBe("");
    expect(screen.getByText(/Costco · \$88\.40 withdraw/)).toBeInTheDocument();
    expect(screen.getByTestId("split-remaining")).toHaveTextContent("Balanced");
  });

  it("shows a deposit as a positive number in the Deposit column", () => {
    renderModal({ transaction: deposit, categories, onClose: () => {}, onSaved: () => {} });
    expect(deposits()[0].value).toBe("500.00");
    expect(withdraws()[0].value).toBe("");
    expect(screen.getByText(/Paycheque · \$500\.00 deposit/)).toBeInTheDocument();
  });

  it("keeps a live tally of what is left to allocate and blocks saving until balanced", () => {
    const onSaved = vi.fn();
    renderModal({ transaction, categories, onClose: () => {}, onSaved });

    fireEvent.change(withdraws()[0], { target: { value: "60" } });

    const remaining = screen.getByTestId("split-remaining");
    expect(remaining).toHaveTextContent("Remaining: $28.40 withdraw");
    expect(remaining).toHaveStyle({ color: "var(--c5)" });

    const saveButton = screen.getByText("Save splits");
    expect(saveButton).toBeDisabled();
    fireEvent.click(saveButton);
    expect(updateSplits).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("reports an over-allocation as remaining in the opposite direction", () => {
    renderModal({ transaction, categories, onClose: () => {}, onSaved: () => {} });
    fireEvent.change(withdraws()[0], { target: { value: "100" } });
    expect(screen.getByTestId("split-remaining")).toHaveTextContent("Remaining: $11.60 deposit");
  });

  it("pre-fills a new split with the remaining amount", () => {
    renderModal({ transaction, categories, onClose: () => {}, onSaved: () => {} });
    fireEvent.change(withdraws()[0], { target: { value: "60" } });
    fireEvent.click(screen.getByText("+ Add split"));

    expect(withdraws()[1].value).toBe("28.40");
    expect(deposits()[1].value).toBe("");
    expect(screen.getByTestId("split-remaining")).toHaveTextContent("Balanced");
  });

  it("moves a negative deposit to the Withdraw column as a positive number", () => {
    renderModal({ transaction, categories, onClose: () => {}, onSaved: () => {} });
    fireEvent.change(withdraws()[0], { target: { value: "60" } });
    fireEvent.click(screen.getByText("+ Add split"));

    fireEvent.change(deposits()[1], { target: { value: "-28.4" } });
    // Counted as a withdrawal while it is still being typed...
    expect(screen.getByTestId("split-remaining")).toHaveTextContent("Balanced");
    // ...and moved across once the field is left.
    fireEvent.blur(deposits()[1]);
    expect(deposits()[1].value).toBe("");
    expect(withdraws()[1].value).toBe("28.40");
  });

  it("moves a negative withdrawal to the Deposit column as a positive number", () => {
    renderModal({ transaction, categories, onClose: () => {}, onSaved: () => {} });
    fireEvent.change(withdraws()[0], { target: { value: "-5" } });
    fireEvent.blur(withdraws()[0]);
    expect(withdraws()[0].value).toBe("");
    expect(deposits()[0].value).toBe("5.00");
  });

  it("clears the other column when an amount is typed", () => {
    renderModal({ transaction, categories, onClose: () => {}, onSaved: () => {} });
    fireEvent.change(deposits()[0], { target: { value: "12" } });
    expect(withdraws()[0].value).toBe("");
    expect(screen.getByTestId("split-remaining")).toHaveTextContent("Remaining: $100.40 withdraw");
  });

  it("saves signed amounts when the splits balance", async () => {
    updateSplits.mockResolvedValue(transaction);
    const onSaved = vi.fn();
    const onClose = vi.fn();
    renderModal({ transaction, categories, onClose, onSaved });

    fireEvent.change(withdraws()[0], { target: { value: "100" } });
    fireEvent.click(screen.getByText("+ Add split")); // a $11.60 refund-style deposit
    pickHousehold(1);
    expect(deposits()[1].value).toBe("11.60");

    fireEvent.click(screen.getByText("Save splits"));

    await vi.waitFor(() => expect(updateSplits).toHaveBeenCalledTimes(1));
    expect(updateSplits).toHaveBeenCalledWith(10, [
      { category_id: 2, amount: -100 },
      { category_id: 3, amount: 11.6 },
    ]);
    await vi.waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(onClose).toHaveBeenCalled();
  });

  it("removes a split row", () => {
    renderModal({ transaction, categories, onClose: () => {}, onSaved: () => {} });
    fireEvent.click(screen.getByText("+ Add split"));
    expect(screen.getAllByText("🗑")).toHaveLength(2);

    fireEvent.click(screen.getAllByText("🗑")[1]);
    expect(screen.queryAllByText("🗑")).toHaveLength(0); // single row left, no remove button
  });

  it("triggers the rule-learning check after a single-split save with a category", async () => {
    updateSplits.mockResolvedValue(transaction);
    renderModal({ transaction, categories, onClose: () => {}, onSaved: () => {} });

    fireEvent.click(screen.getByText("Save splits")); // already 1 row, category_id=2 from fixture

    await vi.waitFor(() => expect(updateSplits).toHaveBeenCalledWith(10, [{ category_id: 2, amount: -88.4 }]));
    await vi.waitFor(() => expect(learnCheck).toHaveBeenCalledWith(10));
  });

  it("does not trigger the rule-learning check on a multi-split save", async () => {
    updateSplits.mockResolvedValue(transaction);
    renderModal({ transaction, categories, onClose: () => {}, onSaved: () => {} });

    fireEvent.change(withdraws()[0], { target: { value: "60.00" } });
    fireEvent.click(screen.getByText("+ Add split"));
    pickHousehold(1);

    fireEvent.click(screen.getByText("Save splits"));

    await vi.waitFor(() => expect(updateSplits).toHaveBeenCalled());
    expect(learnCheck).not.toHaveBeenCalled();
  });
});

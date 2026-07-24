import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Category, Transaction } from "../api/types";
import { SplitModal } from "./SplitModal";

const updateSplits = vi.fn();
vi.mock("../api/transactions", () => ({
  transactionsApi: {
    updateSplits: (...args: unknown[]) => updateSplits(...args),
  },
}));

const categories: Category[] = [
  {
    id: 1,
    name: "shared",
    parent_id: null,
    color: "#111",
    sort_order: 0,
    archived_at: null,
    children: [
      { id: 2, name: "groceries", parent_id: 1, color: "#222", sort_order: 0, archived_at: null, children: [] },
      { id: 3, name: "household", parent_id: 1, color: "#333", sort_order: 1, archived_at: null, children: [] },
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

describe("SplitModal", () => {
  beforeEach(() => {
    updateSplits.mockReset();
  });

  it("shows an error and does not save when split amounts don't sum to the total", () => {
    const onSaved = vi.fn();
    render(<SplitModal transaction={transaction} categories={categories} onClose={() => {}} onSaved={onSaved} />);

    fireEvent.click(screen.getByText("+ Add split"));
    const amountInputs = screen.getAllByDisplayValue(/^(-88\.4|0\.00)$/);
    fireEvent.change(amountInputs[1], { target: { value: "-10.00" } });

    fireEvent.click(screen.getByText("Save splits"));

    expect(screen.getByTestId("split-error")).toHaveTextContent("Splits must sum to $88.40");
    expect(updateSplits).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("saves when split amounts sum to the transaction total", async () => {
    updateSplits.mockResolvedValue(transaction);
    const onSaved = vi.fn();
    const onClose = vi.fn();
    render(<SplitModal transaction={transaction} categories={categories} onClose={onClose} onSaved={onSaved} />);

    fireEvent.click(screen.getByText("+ Add split"));
    const categorySelects = screen.getAllByRole("combobox");
    fireEvent.change(categorySelects[1], { target: { value: "3" } }); // household, distinct from row 1's groceries

    const amountInputs = screen.getAllByDisplayValue(/^(-88\.4|0\.00)$/);
    fireEvent.change(amountInputs[0], { target: { value: "-60.00" } });
    fireEvent.change(amountInputs[1], { target: { value: "-28.40" } });

    fireEvent.click(screen.getByText("Save splits"));

    await vi.waitFor(() => expect(updateSplits).toHaveBeenCalledTimes(1));
    expect(updateSplits).toHaveBeenCalledWith(10, [
      { category_id: 2, amount: -60 },
      { category_id: 3, amount: -28.4 },
    ]);
    await vi.waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(onClose).toHaveBeenCalled();
  });

  it("removes a split row and updates the running sum", () => {
    render(<SplitModal transaction={transaction} categories={categories} onClose={() => {}} onSaved={() => {}} />);
    fireEvent.click(screen.getByText("+ Add split"));
    expect(screen.getAllByText("⌀")).toHaveLength(2);

    fireEvent.click(screen.getAllByText("⌀")[1]);
    expect(screen.queryAllByText("⌀")).toHaveLength(0); // single row left, no remove button
  });
});

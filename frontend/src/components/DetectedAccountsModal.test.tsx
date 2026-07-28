import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Account, DetectedAccount } from "../api/types";
import { DetectedAccountsModal } from "./DetectedAccountsModal";

const existingAccounts: Account[] = [
  { id: 1, name: "Main checking", account_number: null, type: "asset", opening_balance: 0, color: "#4f8a9c", balance: 0 },
];

const accounts: DetectedAccount[] = [
  { parsed_name: "Main checking", transaction_count: 12, matched_account_id: 1, suggested_type: "asset" },
  { parsed_name: "Credit Card", transaction_count: 3, matched_account_id: null, suggested_type: "liability" },
];

function renderModal(props: Partial<Parameters<typeof DetectedAccountsModal>[0]> = {}) {
  return render(
    <DetectedAccountsModal
      accounts={accounts}
      existingAccounts={existingAccounts}
      onClose={() => {}}
      onConfirm={() => {}}
      {...props}
    />,
  );
}

describe("DetectedAccountsModal", () => {
  it("shows matched accounts as read-only and new accounts as an editable form", () => {
    renderModal();
    expect(screen.getByText(/matched to Main checking/)).toBeInTheDocument();
    expect(screen.getByDisplayValue("Credit Card")).toBeInTheDocument(); // pre-filled name input
  });

  it("submits a mapping resolution for matched accounts and a new_account resolution for new ones", () => {
    const onConfirm = vi.fn();
    renderModal({ onConfirm });

    fireEvent.change(screen.getByDisplayValue("Credit Card"), { target: { value: "My Credit Card" } });
    fireEvent.click(screen.getByText("Import"));

    expect(onConfirm).toHaveBeenCalledWith([
      { parsed_name: "Main checking", account_id: 1 },
      {
        parsed_name: "Credit Card",
        new_account: { name: "My Credit Card", type: "liability", opening_balance: 0, color: "#4f8a9c" },
      },
    ]);
  });

  it("falls back to the parsed name if the name field is cleared", () => {
    const onConfirm = vi.fn();
    renderModal({ onConfirm });

    fireEvent.change(screen.getByDisplayValue("Credit Card"), { target: { value: "   " } });
    fireEvent.click(screen.getByText("Import"));

    expect(onConfirm.mock.calls[0][0][1].new_account.name).toBe("Credit Card");
  });

  it("disables Import while submitting", () => {
    renderModal({ submitting: true });
    expect(screen.getByText("Importing…")).toBeDisabled();
  });
});

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Account, DetectAccountsResponse, DetectedAccount } from "../api/types";
import { ImportReviewModal } from "./ImportReviewModal";

const existingAccounts: Account[] = [
  {
    id: 1,
    name: "Main checking",
    account_number: null,
    type: "asset",
    opening_balance: 0,
    color: "#4f8a9c",
    balance: 0,
  },
  {
    id: 2,
    name: "Visa",
    account_number: null,
    type: "liability",
    opening_balance: 0,
    color: "#c04f4f",
    balance: 0,
  },
];

const detected: DetectedAccount[] = [
  {
    parsed_name: "Main checking",
    transaction_count: 12,
    matched_account_id: 1,
    match_reason: "name",
    suggested_type: "asset",
    target_account_id: 1,
    new_count: 9,
    duplicate_count: 2,
    needs_review_count: 1,
  },
  {
    parsed_name: "Credit Card",
    transaction_count: 3,
    matched_account_id: null,
    match_reason: null,
    suggested_type: "liability",
    target_account_id: null,
    new_count: 3,
    duplicate_count: 0,
    needs_review_count: 0,
  },
];

function renderModal(props: Partial<Parameters<typeof ImportReviewModal>[0]> = {}) {
  const detection: DetectAccountsResponse = { has_account_sections: true, accounts: detected };
  return render(
    <ImportReviewModal
      filename="statement.qif"
      detection={detection}
      existingAccounts={existingAccounts}
      onTargetsChange={() => {}}
      onClose={() => {}}
      onConfirm={() => {}}
      {...props}
    />,
  );
}

describe("ImportReviewModal", () => {
  it("shows the auto-match and the per-account transaction breakdown", () => {
    const { container } = renderModal();
    expect(screen.getByText(/auto-matched by name/)).toBeInTheDocument();
    const matched = screen.getByLabelText("Import Main checking into") as HTMLSelectElement;
    expect(matched.value).toBe("1");
    // The counts are wrapped in <b>, so match against the flattened text.
    expect(container.textContent).toMatch(/9 to import · 2 duplicates skipped · 1 needs attention/);
  });

  it("defaults an unmatched account to creating a new one, pre-filled from the parsed name", () => {
    renderModal();
    const unmatched = screen.getByLabelText("Import Credit Card into") as HTMLSelectElement;
    expect(unmatched.value).toBe("new");
    expect(screen.getByDisplayValue("Credit Card")).toBeInTheDocument();
  });

  it("lets the user override a match and asks the parent to recompute the preview", () => {
    const onTargetsChange = vi.fn();
    renderModal({ onTargetsChange });

    fireEvent.change(screen.getByLabelText("Import Main checking into"), { target: { value: "2" } });

    expect(onTargetsChange).toHaveBeenCalledWith([
      { parsed_name: "Main checking", account_id: 2 },
      { parsed_name: "Credit Card", account_id: null },
    ]);
    expect(screen.getByText("overridden")).toBeInTheDocument();
    // Counts were computed for account 1, so they're withheld until the refetch.
    expect(screen.getByText("Recalculating…")).toBeInTheDocument();
  });

  it("submits a mapping for chosen accounts and a new_account for the rest", () => {
    const onConfirm = vi.fn();
    renderModal({ onConfirm });

    fireEvent.change(screen.getByDisplayValue("Credit Card"), { target: { value: "My Credit Card" } });
    fireEvent.click(screen.getByText("Import"));

    expect(onConfirm).toHaveBeenCalledWith([
      { parsed_name: "Main checking", account_id: 1 },
      {
        parsed_name: "Credit Card",
        new_account: {
          name: "My Credit Card",
          account_number: null,
          type: "liability",
          opening_balance: 0,
          color: "#4f8a9c",
        },
      },
    ]);
  });

  it("includes an account number when the user fills it in", () => {
    const onConfirm = vi.fn();
    renderModal({ onConfirm });

    fireEvent.change(screen.getByPlaceholderText("Bank account number / identifier"), {
      target: { value: "1234567890" },
    });
    fireEvent.click(screen.getByText("Import"));

    expect(onConfirm.mock.calls[0][0][1].new_account.account_number).toBe("1234567890");
  });

  it("falls back to the parsed name if the name field is cleared", () => {
    const onConfirm = vi.fn();
    renderModal({ onConfirm });

    fireEvent.change(screen.getByDisplayValue("Credit Card"), { target: { value: "   " } });
    fireEvent.click(screen.getByText("Import"));

    expect(onConfirm.mock.calls[0][0][1].new_account.name).toBe("Credit Card");
  });

  it("prompts for a destination for a file with no account sections", () => {
    render(
      <ImportReviewModal
        filename="statement.qif"
        detection={{
          has_account_sections: false,
          accounts: [
            {
              parsed_name: null,
              transaction_count: 4,
              matched_account_id: null,
              match_reason: null,
              suggested_type: null,
              target_account_id: null,
              new_count: 4,
              duplicate_count: 0,
              needs_review_count: 0,
            },
          ],
        }}
        existingAccounts={existingAccounts}
        onTargetsChange={() => {}}
        onClose={() => {}}
        onConfirm={() => {}}
      />,
    );
    expect(screen.getByText(/no account sections/)).toBeInTheDocument();
    expect(screen.getByLabelText("Import All transactions into")).toBeInTheDocument();
  });

  it("disables Import while submitting", () => {
    renderModal({ submitting: true });
    expect(screen.getByText("Importing…")).toBeDisabled();
  });
});

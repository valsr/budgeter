import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { Account, Transaction } from "../api/types";
import { LinkTransferModal } from "./LinkTransferModal";

const transferCandidates = vi.fn();
const linkTransfer = vi.fn();
vi.mock("../api/transactions", () => ({
  transactionsApi: {
    transferCandidates: (...args: unknown[]) => transferCandidates(...args),
    linkTransfer: (...args: unknown[]) => linkTransfer(...args),
  },
}));

const accounts: Account[] = [
  { id: 1, name: "Main", account_number: null, type: "asset", opening_balance: 0, color: "#111", balance: 0 },
  { id: 2, name: "Home", account_number: null, type: "asset", opening_balance: 0, color: "#222", balance: 0 },
];

function txn(overrides: Partial<Transaction> & { id: number; account_id: number; amount: number }): Transaction {
  const { amount, ...rest } = overrides;
  return {
    date: "2026-01-19",
    name: "UU500 TFR-TO 6000884",
    type: "normal",
    transfer_pair_id: null,
    splits: [{ id: overrides.id * 10, category_id: null, amount, suggested_category_id: null, suggestion_source: null }],
    ...rest,
  };
}

const source = txn({ id: 1, account_id: 1, amount: -6594.96 });
const candidate = txn({ id: 2, account_id: 2, amount: 6594.96, name: "UU500 TFR-FR 6263382", date: "2026-01-20" });

beforeEach(() => {
  transferCandidates.mockReset();
  linkTransfer.mockReset().mockResolvedValue([]);
});

it("lists candidates and links the selected one", async () => {
  transferCandidates.mockResolvedValue([candidate]);
  const onLinked = vi.fn();
  render(
    <LinkTransferModal transaction={source} accounts={accounts} onClose={vi.fn()} onLinked={onLinked} />,
  );

  await screen.findByText("UU500 TFR-FR 6263382");
  fireEvent.click(screen.getByLabelText("Link with UU500 TFR-FR 6263382"));
  fireEvent.click(screen.getByRole("button", { name: "Link as transfer" }));

  await waitFor(() => expect(linkTransfer).toHaveBeenCalledWith(1, 2));
  await waitFor(() => expect(onLinked).toHaveBeenCalled());
});

it("does not preselect a candidate, so a wrong pairing needs a deliberate click", async () => {
  transferCandidates.mockResolvedValue([candidate]);
  render(<LinkTransferModal transaction={source} accounts={accounts} onClose={vi.fn()} onLinked={vi.fn()} />);

  await screen.findByText("UU500 TFR-FR 6263382");
  expect(screen.getByLabelText("Link with UU500 TFR-FR 6263382")).not.toBeChecked();
  expect(screen.queryByRole("button", { name: "Link as transfer" })).toBeNull();
});

it("widens the date window on request", async () => {
  transferCandidates.mockResolvedValueOnce([]).mockResolvedValueOnce([candidate]);
  render(<LinkTransferModal transaction={source} accounts={accounts} onClose={vi.fn()} onLinked={vi.fn()} />);

  fireEvent.click(await screen.findByRole("button", { name: "Search 30 days" }));

  await waitFor(() => expect(transferCandidates).toHaveBeenLastCalledWith(1, 30));
  await screen.findByText("UU500 TFR-FR 6263382");
});

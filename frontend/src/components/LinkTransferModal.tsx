import { useEffect, useMemo, useState } from "react";
import { transactionsApi } from "../api/transactions";
import type { Account, Transaction } from "../api/types";
import { hexToRgba } from "./CategoryTag";
import { Modal } from "./Modal";

const DEFAULT_ACCOUNT_COLOR = "#4f8a9c";
const NARROW_WINDOW = 5;
const WIDE_WINDOW = 30;

interface LinkTransferModalProps {
  transaction: Transaction;
  accounts: Account[];
  onClose: () => void;
  onLinked: () => void;
}

/** Pick the other leg of a transfer whose two sides were imported separately
 * — one from each account's own statement — and link them into a pair. */
export function LinkTransferModal({ transaction, accounts, onClose, onLinked }: LinkTransferModalProps) {
  const [dayWindow, setDayWindow] = useState(NARROW_WINDOW);
  const [candidates, setCandidates] = useState<Transaction[] | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [linking, setLinking] = useState(false);

  const accountById = useMemo(() => new Map(accounts.map((a) => [a.id, a])), [accounts]);
  const amount = transaction.splits.reduce((sum, s) => sum + s.amount, 0);

  useEffect(() => {
    let cancelled = false;
    setCandidates(null);
    transactionsApi.transferCandidates(transaction.id, dayWindow).then((items) => {
      if (cancelled) return;
      setCandidates(items);
      // Don't preselect: an equal-and-opposite amount nearby is suggestive,
      // not proof, and a wrong pairing silently removes real spending from
      // the budget. Make the user choose.
      setSelectedId(null);
    });
    return () => {
      cancelled = true;
    };
  }, [transaction.id, dayWindow]);

  async function link() {
    if (selectedId === null) return;
    setLinking(true);
    try {
      await transactionsApi.linkTransfer(transaction.id, selectedId);
      onLinked();
    } finally {
      setLinking(false);
    }
  }

  function accountTag(accountId: number) {
    const account = accountById.get(accountId);
    if (!account) return null;
    const color = account.color ?? DEFAULT_ACCOUNT_COLOR;
    return (
      <span className="tag" style={{ background: hexToRgba(color, 0.15), color }}>
        {account.name}
      </span>
    );
  }

  return (
    <Modal
      title="Link as transfer"
      onClose={onClose}
      onSubmit={selectedId === null ? undefined : link}
      submitLabel={linking ? "Linking…" : "Link as transfer"}
      submitDisabled={linking}
      wide
    >
      <p className="sub">
        Linking marks both transactions as one transfer between accounts. They keep their amounts but
        drop any category, and stop counting as spending in budgets.
      </p>

      <table>
        <tbody>
          <tr>
            <td style={{ width: 90 }}>{transaction.date}</td>
            <td>{transaction.name}</td>
            <td style={{ width: 160 }}>{accountTag(transaction.account_id)}</td>
            <td className="right" style={{ width: 110 }}>
              {amount < 0 ? "−" : "+"}${Math.abs(amount).toFixed(2)}
            </td>
          </tr>
        </tbody>
      </table>

      <h3 style={{ margin: "18px 0 6px", fontSize: 13 }}>
        Matching transactions on other accounts
      </h3>

      {candidates === null && <p className="sub">Searching…</p>}

      {candidates !== null && candidates.length === 0 && (
        <p className="sub">
          No transaction on another account has the opposite amount within {dayWindow} days.{" "}
          {dayWindow < WIDE_WINDOW && (
            <button type="button" className="btn ghost sm" onClick={() => setDayWindow(WIDE_WINDOW)}>
              Search {WIDE_WINDOW} days
            </button>
          )}
        </p>
      )}

      {candidates !== null && candidates.length > 0 && (
        <table>
          <thead>
            <tr>
              <th style={{ width: 32 }}></th>
              <th>Date</th>
              <th>Name</th>
              <th>Account</th>
              <th className="right">Amount</th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((candidate) => {
              const candidateAmount = candidate.splits.reduce((sum, s) => sum + s.amount, 0);
              return (
                <tr
                  key={candidate.id}
                  style={{ cursor: "pointer" }}
                  onClick={() => setSelectedId(candidate.id)}
                >
                  <td>
                    <input
                      type="radio"
                      name="transfer-candidate"
                      aria-label={`Link with ${candidate.name}`}
                      checked={selectedId === candidate.id}
                      onChange={() => setSelectedId(candidate.id)}
                    />
                  </td>
                  <td>{candidate.date}</td>
                  <td>{candidate.name}</td>
                  <td>{accountTag(candidate.account_id)}</td>
                  <td className="right">
                    {candidateAmount < 0 ? "−" : "+"}${Math.abs(candidateAmount).toFixed(2)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {candidates !== null && candidates.length > 0 && dayWindow < WIDE_WINDOW && (
        <p className="sub" style={{ marginTop: 10 }}>
          Not here?{" "}
          <button type="button" className="btn ghost sm" onClick={() => setDayWindow(WIDE_WINDOW)}>
            Search {WIDE_WINDOW} days
          </button>
        </p>
      )}
    </Modal>
  );
}

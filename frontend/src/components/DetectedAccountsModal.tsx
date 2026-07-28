import { useState } from "react";
import type { Account, AccountType, DetectedAccount, ImportResolutionInput } from "../api/types";
import { Modal } from "./Modal";

interface NewAccountForm {
  name: string;
  type: AccountType;
  opening_balance: string;
  color: string;
}

const DEFAULT_COLOR = "#4f8a9c";

function defaultForm(detected: DetectedAccount): NewAccountForm {
  return {
    name: detected.parsed_name ?? "",
    type: detected.suggested_type ?? "asset",
    opening_balance: "0.00",
    color: DEFAULT_COLOR,
  };
}

interface DetectedAccountsModalProps {
  accounts: DetectedAccount[];
  existingAccounts: Account[];
  submitting?: boolean;
  onClose: () => void;
  onConfirm: (resolutions: ImportResolutionInput[]) => void;
}

export function DetectedAccountsModal({
  accounts,
  existingAccounts,
  submitting,
  onClose,
  onConfirm,
}: DetectedAccountsModalProps) {
  const [forms, setForms] = useState<Record<number, NewAccountForm>>(() => {
    const initial: Record<number, NewAccountForm> = {};
    accounts.forEach((a, i) => {
      if (a.matched_account_id === null) initial[i] = defaultForm(a);
    });
    return initial;
  });

  function updateForm(i: number, patch: Partial<NewAccountForm>) {
    setForms((prev) => ({ ...prev, [i]: { ...prev[i], ...patch } }));
  }

  function accountName(id: number): string {
    return existingAccounts.find((a) => a.id === id)?.name ?? `#${id}`;
  }

  function submit() {
    const resolutions: ImportResolutionInput[] = accounts.map((a, i) => {
      if (a.matched_account_id !== null) {
        return { parsed_name: a.parsed_name, account_id: a.matched_account_id };
      }
      const form = forms[i];
      return {
        parsed_name: a.parsed_name,
        new_account: {
          name: form.name.trim() || a.parsed_name || "Untitled account",
          type: form.type,
          opening_balance: parseFloat(form.opening_balance) || 0,
          color: form.color,
        },
      };
    });
    onConfirm(resolutions);
  }

  const newCount = accounts.filter((a) => a.matched_account_id === null).length;

  return (
    <Modal
      title="New accounts detected"
      onClose={onClose}
      onSubmit={submit}
      submitLabel={submitting ? "Importing…" : "Import"}
      submitDisabled={submitting}
      wide
    >
      <p className="sub" style={{ marginBottom: 14 }}>
        This file references {accounts.length} account{accounts.length === 1 ? "" : "s"}
        {newCount > 0 && (
          <>
            {" "}
            — {newCount} {newCount === 1 ? "is new" : "are new"}. Review the name and details below before
            importing.
          </>
        )}
      </p>

      {accounts.map((a, i) => {
        const isNew = a.matched_account_id === null;
        return (
          <div
            key={i}
            className="card"
            style={{ marginBottom: 12, borderColor: isNew ? "var(--c2)" : "var(--line)" }}
          >
            {!isNew ? (
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span>
                  <b>{a.parsed_name}</b> <span className="sub">({a.transaction_count} transactions)</span>
                </span>
                <span className="tag" style={{ background: "var(--c4bg)", color: "var(--c4)" }}>
                  matched to {accountName(a.matched_account_id as number)}
                </span>
              </div>
            ) : (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
                  <span className="sub">
                    New account · {a.transaction_count} transaction{a.transaction_count === 1 ? "" : "s"}
                    {a.parsed_name && a.parsed_name !== forms[i]?.name ? ` (parsed as "${a.parsed_name}")` : ""}
                  </span>
                </div>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
                  <div className="field" style={{ flex: 2, minWidth: 160, marginBottom: 0 }}>
                    <label>Name</label>
                    <input
                      value={forms[i]?.name ?? ""}
                      onChange={(e) => updateForm(i, { name: e.target.value })}
                      placeholder="e.g. Chase Checking"
                    />
                  </div>
                  <div className="field" style={{ flex: 1, minWidth: 120, marginBottom: 0 }}>
                    <label>Type</label>
                    <select
                      value={forms[i]?.type ?? "asset"}
                      onChange={(e) => updateForm(i, { type: e.target.value as AccountType })}
                    >
                      <option value="asset">Asset</option>
                      <option value="liability">Liability</option>
                    </select>
                  </div>
                  <div className="field" style={{ flex: 1, minWidth: 110, marginBottom: 0 }}>
                    <label>Opening balance</label>
                    <input
                      value={forms[i]?.opening_balance ?? "0.00"}
                      onChange={(e) => updateForm(i, { opening_balance: e.target.value })}
                    />
                  </div>
                  <div className="field" style={{ marginBottom: 0 }}>
                    <label>Colour</label>
                    <input
                      type="color"
                      value={forms[i]?.color ?? DEFAULT_COLOR}
                      style={{ width: 60, padding: 2 }}
                      onChange={(e) => updateForm(i, { color: e.target.value })}
                    />
                  </div>
                </div>
              </>
            )}
          </div>
        );
      })}
    </Modal>
  );
}

import { useState } from "react";
import type {
  Account,
  AccountType,
  DetectAccountsOverride,
  DetectAccountsResponse,
  DetectedAccount,
  ImportResolutionInput,
} from "../api/types";
import { Modal } from "./Modal";

interface NewAccountForm {
  name: string;
  account_number: string;
  type: AccountType;
  opening_balance: string;
  color: string;
}

const DEFAULT_COLOR = "#4f8a9c";
const NEW = "new" as const;

/** The account a detected block will be imported into: an existing account id,
 * or "new" meaning "create one from the form below". */
type Target = number | typeof NEW;

function defaultForm(detected: DetectedAccount): NewAccountForm {
  return {
    name: detected.parsed_name ?? "",
    account_number: "",
    type: detected.suggested_type ?? "asset",
    opening_balance: "0.00",
    color: DEFAULT_COLOR,
  };
}

function targetsToOverrides(
  accounts: DetectedAccount[],
  targets: Record<number, Target>,
): DetectAccountsOverride[] {
  return accounts.map((a, i) => ({
    parsed_name: a.parsed_name,
    account_id: targets[i] === NEW ? null : (targets[i] as number),
  }));
}

interface ImportReviewModalProps {
  filename: string;
  detection: DetectAccountsResponse;
  existingAccounts: Account[];
  /** True while the parent is re-running the preview for changed targets. */
  previewing?: boolean;
  submitting?: boolean;
  onTargetsChange: (overrides: DetectAccountsOverride[]) => void;
  onClose: () => void;
  onConfirm: (resolutions: ImportResolutionInput[]) => void;
}

export function ImportReviewModal({
  filename,
  detection,
  existingAccounts,
  previewing,
  submitting,
  onTargetsChange,
  onClose,
  onConfirm,
}: ImportReviewModalProps) {
  const accounts = detection.accounts;

  // Seeded from the server's auto-match, then owned here — later `detection`
  // props are refreshed counts for these same targets, not new suggestions.
  const [targets, setTargets] = useState<Record<number, Target>>(() => {
    const initial: Record<number, Target> = {};
    accounts.forEach((a, i) => {
      initial[i] = a.matched_account_id ?? NEW;
    });
    return initial;
  });

  const [forms, setForms] = useState<Record<number, NewAccountForm>>(() => {
    const initial: Record<number, NewAccountForm> = {};
    accounts.forEach((a, i) => {
      initial[i] = defaultForm(a);
    });
    return initial;
  });

  function updateForm(i: number, patch: Partial<NewAccountForm>) {
    setForms((prev) => ({ ...prev, [i]: { ...prev[i], ...patch } }));
  }

  function changeTarget(i: number, target: Target) {
    const next = { ...targets, [i]: target };
    setTargets(next);
    onTargetsChange(targetsToOverrides(accounts, next));
  }

  function submit() {
    const resolutions: ImportResolutionInput[] = accounts.map((a, i) => {
      const target = targets[i];
      if (target !== NEW) {
        return { parsed_name: a.parsed_name, account_id: target };
      }
      const form = forms[i];
      return {
        parsed_name: a.parsed_name,
        new_account: {
          name: form.name.trim() || a.parsed_name || "Untitled account",
          account_number: form.account_number.trim() || null,
          type: form.type,
          opening_balance: parseFloat(form.opening_balance) || 0,
          color: form.color,
        },
      };
    });
    onConfirm(resolutions);
  }

  const label = (a: DetectedAccount) =>
    a.parsed_name ?? (detection.has_account_sections ? "Unnamed section" : "All transactions");

  const totals = accounts.reduce(
    (acc, a) => ({
      rows: acc.rows + a.transaction_count,
      imported: acc.imported + a.new_count,
      duplicates: acc.duplicates + a.duplicate_count,
      review: acc.review + a.needs_review_count,
    }),
    { rows: 0, imported: 0, duplicates: 0, review: 0 },
  );

  return (
    <Modal
      title="Review import"
      onClose={onClose}
      onSubmit={submit}
      submitLabel={submitting ? "Importing…" : "Import"}
      submitDisabled={submitting}
      wide
    >
      <p className="sub" style={{ marginBottom: 14 }}>
        <b>{filename}</b> — {accounts.length} account{accounts.length === 1 ? "" : "s"},{" "}
        {totals.rows} transaction{totals.rows === 1 ? "" : "s"}
        {detection.has_account_sections
          ? ". Confirm where each one goes; matches are pre-selected and can be changed."
          : ". This file has no account sections — choose where its transactions go."}
      </p>

      {accounts.map((a, i) => {
        const target = targets[i];
        const isNew = target === NEW;
        const autoMatched = a.matched_account_id !== null && target === a.matched_account_id;
        const overridden = a.matched_account_id !== null && target !== a.matched_account_id;
        // Counts came back for a different target than what's selected now, so
        // they describe the wrong account until the parent's refetch lands.
        const stale =
          previewing || a.target_account_id !== (isNew ? null : (target as number));

        return (
          <div
            key={i}
            className="card"
            style={{ marginBottom: 12, borderColor: isNew ? "var(--c2)" : "var(--line)" }}
          >
            <div
              style={{
                display: "flex",
                gap: 10,
                alignItems: "center",
                flexWrap: "wrap",
                marginBottom: 10,
              }}
            >
              <b>{label(a)}</b>
              <span className="sub">
                {a.transaction_count} transaction{a.transaction_count === 1 ? "" : "s"}
              </span>
              <span style={{ flex: 1 }} />
              <label className="sub" htmlFor={`import-target-${i}`}>
                Import into
              </label>
              <select
                id={`import-target-${i}`}
                aria-label={`Import ${label(a)} into`}
                value={isNew ? NEW : String(target)}
                onChange={(e) =>
                  changeTarget(i, e.target.value === NEW ? NEW : Number(e.target.value))
                }
              >
                {existingAccounts.map((acc) => (
                  <option key={acc.id} value={acc.id}>
                    {acc.name}
                  </option>
                ))}
                <option value={NEW}>+ Create new account</option>
              </select>
            </div>

            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              {autoMatched && (
                <span className="tag" style={{ background: "var(--c4bg)", color: "var(--c4)" }}>
                  auto-matched by {a.match_reason === "account_number" ? "account number" : "name"}
                </span>
              )}
              {overridden && <span className="tag">overridden</span>}
              {stale ? (
                <span className="sub">Recalculating…</span>
              ) : (
                <span className="sub">
                  <b>{a.new_count}</b> to import · <b>{a.duplicate_count}</b> duplicate
                  {a.duplicate_count === 1 ? "" : "s"} skipped · <b>{a.needs_review_count}</b> need
                  {a.needs_review_count === 1 ? "s" : ""} attention
                </span>
              )}
            </div>

            {isNew && (
              <div
                style={{
                  display: "flex",
                  gap: 10,
                  flexWrap: "wrap",
                  alignItems: "flex-end",
                  marginTop: 12,
                }}
              >
                <div className="field" style={{ flex: 2, minWidth: 160, marginBottom: 0 }}>
                  <label>Name</label>
                  <input
                    value={forms[i]?.name ?? ""}
                    onChange={(e) => updateForm(i, { name: e.target.value })}
                    placeholder="e.g. Chase Checking"
                  />
                </div>
                <div className="field" style={{ flex: 2, minWidth: 140, marginBottom: 0 }}>
                  <label>Account ID</label>
                  <input
                    value={forms[i]?.account_number ?? ""}
                    onChange={(e) => updateForm(i, { account_number: e.target.value })}
                    placeholder="Bank account number / identifier"
                  />
                </div>
                <div className="field" style={{ flex: 1, minWidth: 120, marginBottom: 0 }}>
                  <label>Type</label>
                  <select
                    aria-label={`Type for ${label(a)}`}
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
            )}
          </div>
        );
      })}

      {accounts.length > 1 && !previewing && (
        <p className="sub">
          Total: <b>{totals.imported}</b> to import · <b>{totals.duplicates}</b> duplicate
          {totals.duplicates === 1 ? "" : "s"} skipped · <b>{totals.review}</b> needing attention.
        </p>
      )}
    </Modal>
  );
}

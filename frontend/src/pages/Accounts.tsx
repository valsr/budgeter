import { useEffect, useState } from "react";
import { DEFAULT_ACCOUNT_COLOR, accountsApi } from "../api/accounts";
import type { Account } from "../api/types";
import { hexToRgba } from "../components/CategoryTag";
import { Modal } from "../components/Modal";
import { SplitModal } from "../components/SplitModal";
import { TransactionTable } from "../components/TransactionTable";
import { ACCOUNTING_PERIOD_START, useLedgerData } from "../hooks/useLedgerData";

function fmtBal(n: number): string {
  const sign = n < 0 ? "-" : "";
  return `${sign}$${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

interface AccountFormState {
  name: string;
  account_number: string;
  type: "asset" | "liability";
  opening_balance: string;
  color: string;
}

const EMPTY_FORM: AccountFormState = {
  name: "",
  account_number: "",
  type: "asset",
  opening_balance: "0.00",
  color: DEFAULT_ACCOUNT_COLOR,
};

export function Accounts() {
  const { accounts, categories, loadAccounts, loadCategories, splitTxn, setSplitTxn, refreshKey, refresh } =
    useLedgerData();
  const [currentAccountId, setCurrentAccountId] = useState<number | null>(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [modal, setModal] = useState<null | "new" | "edit">(null);
  const [form, setForm] = useState<AccountFormState>(EMPTY_FORM);
  const [accountIdTouched, setAccountIdTouched] = useState(false);

  // Start on the first account once they've loaded.
  useEffect(() => {
    if (currentAccountId === null && accounts.length > 0) setCurrentAccountId(accounts[0].id);
  }, [accounts, currentAccountId]);

  const currentAccount = accounts.find((a) => a.id === currentAccountId);

  function openNewModal() {
    setForm(EMPTY_FORM);
    setAccountIdTouched(false);
    setModal("new");
  }

  function openEditModal(account: Account) {
    setForm({
      name: account.name,
      account_number: account.account_number ?? "",
      type: account.type,
      opening_balance: String(account.opening_balance),
      color: account.color ?? DEFAULT_ACCOUNT_COLOR,
    });
    setAccountIdTouched(true);
    setModal("edit");
  }

  async function saveAccount() {
    const payload = {
      name: form.name,
      account_number: form.account_number || null,
      type: form.type,
      opening_balance: parseFloat(form.opening_balance) || 0,
      color: form.color,
    };
    if (modal === "new") {
      const created = await accountsApi.create(payload);
      setModal(null);
      loadAccounts();
      setCurrentAccountId(created.id);
    } else if (modal === "edit" && currentAccount) {
      await accountsApi.update(currentAccount.id, payload);
      setModal(null);
      loadAccounts();
    }
  }

  return (
    <div>
      <h1>Accounts</h1>
      <p className="sub">Pick an account below — the transaction list is pre-filtered to it.</p>

      <div style={{ display: "flex", alignItems: "flex-start", gap: 10, marginBottom: 18 }}>
        <div className="acct-select">
          <div className="acct-select-btn" onClick={() => setDropdownOpen((o) => !o)}>
            {currentAccount ? (
              <span>
                <span
                  className="tag"
                  style={{
                    background: hexToRgba(currentAccount.color ?? DEFAULT_ACCOUNT_COLOR, 0.15),
                    color: currentAccount.color ?? DEFAULT_ACCOUNT_COLOR,
                  }}
                >
                  {currentAccount.name}
                </span>
                <span className={"badge " + (currentAccount.type === "asset" ? "asset" : "liab")}>
                  {currentAccount.type}
                </span>{" "}
                <span style={{ color: "var(--ink-2)" }}>{fmtBal(currentAccount.balance)}</span>
              </span>
            ) : (
              <span>No accounts yet</span>
            )}
            <span className="chev">▾</span>
          </div>
          {dropdownOpen && (
            <div className="acct-panel open">
              {accounts.map((a) => (
                <div
                  key={a.id}
                  className="opt"
                  onClick={() => {
                    setCurrentAccountId(a.id);
                    setDropdownOpen(false);
                  }}
                >
                  <span>
                    <span
                      className="tag"
                      style={{
                        background: hexToRgba(a.color ?? DEFAULT_ACCOUNT_COLOR, 0.15),
                        color: a.color ?? DEFAULT_ACCOUNT_COLOR,
                      }}
                    >
                      {a.name}
                    </span>
                    <span className={"badge " + (a.type === "asset" ? "asset" : "liab")}>{a.type}</span>{" "}
                    <span style={{ color: "var(--ink-2)" }}>{fmtBal(a.balance)}</span>
                  </span>
                  <span
                    className="opt-edit"
                    onClick={(e) => {
                      e.stopPropagation();
                      setCurrentAccountId(a.id);
                      openEditModal(a);
                    }}
                  >
                    ✎
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
        <button className="btn" onClick={openNewModal}>
          + New account
        </button>
      </div>

      {currentAccount && (
        <TransactionTable
          categories={categories}
          accounts={accounts}
          lockAccountId={currentAccount.id}
          onSplitTransaction={setSplitTxn}
          refreshKey={refreshKey}
          onDataChanged={loadAccounts}
          onCategoriesChanged={loadCategories}
          initialFilters={{ date_from: ACCOUNTING_PERIOD_START }}
        />
      )}

      {splitTxn && (
        <SplitModal
          transaction={splitTxn}
          categories={categories}
          onClose={() => setSplitTxn(null)}
          onSaved={refresh}
        />
      )}

      {modal && (
        <Modal
          title={modal === "new" ? "New account" : "Edit account"}
          onClose={() => setModal(null)}
          onSubmit={saveAccount}
          submitLabel={modal === "new" ? "Create account" : "Save changes"}
        >
          <div className="field">
            <label>Account name</label>
            <input
              value={form.name}
              onChange={(e) => {
                const name = e.target.value;
                setForm((f) => ({
                  ...f,
                  name,
                  account_number: modal === "new" && !accountIdTouched ? name : f.account_number,
                }));
              }}
            />
          </div>
          <div className="field">
            <label>Account ID</label>
            <input
              value={form.account_number}
              onChange={(e) => {
                setAccountIdTouched(true);
                setForm((f) => ({ ...f, account_number: e.target.value }));
              }}
              placeholder="Bank account number / identifier"
            />
          </div>
          <div className="field">
            <label>Type</label>
            <select
              value={form.type}
              onChange={(e) => setForm((f) => ({ ...f, type: e.target.value as "asset" | "liability" }))}
            >
              <option value="asset">Asset</option>
              <option value="liability">Liability</option>
            </select>
          </div>
          <div className="field">
            <label>Opening balance</label>
            <input
              value={form.opening_balance}
              onChange={(e) => setForm((f) => ({ ...f, opening_balance: e.target.value }))}
            />
          </div>
          <div className="field">
            <label>Colour</label>
            <input
              type="color"
              value={form.color}
              style={{ width: 60, padding: 2 }}
              onChange={(e) => setForm((f) => ({ ...f, color: e.target.value }))}
            />
          </div>
        </Modal>
      )}
    </div>
  );
}

import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { accountsApi } from "../api/accounts";
import { categoriesApi } from "../api/categories";
import type { Account, Category, Transaction } from "../api/types";
import { RunRulesModal } from "../components/RunRulesModal";
import { SplitModal } from "../components/SplitModal";
import { TransactionTable } from "../components/TransactionTable";

export function Transactions() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [splitTxn, setSplitTxn] = useState<Transaction | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [showRunRulesModal, setShowRunRulesModal] = useState(false);
  const [searchParams] = useSearchParams();

  function loadCategories() {
    // include_archived so historical transactions keep rendering their
    // (possibly archived) category; pickers filter to active internally.
    categoriesApi.list(true).then(setCategories);
  }

  useEffect(() => {
    accountsApi.list().then(setAccounts);
    loadCategories();
  }, []);

  // The Overview banner links here as /transactions?uncategorized=1 —
  // start with the Categorized toggle off so only uncategorized rows show.
  const uncategorizedOnly = searchParams.get("uncategorized") === "1";

  return (
    <div>
      <h1>Transactions</h1>
      <p className="sub">All accounts. Filter, search, split, and review categorization suggestions.</p>

      <TransactionTable
        categories={categories}
        accounts={accounts}
        onSplitTransaction={setSplitTxn}
        refreshKey={refreshKey}
        onCategoriesChanged={loadCategories}
        initialFilters={uncategorizedOnly ? { show_categorized: false } : undefined}
        filterRowExtra={
          <button className="btn ghost sm" onClick={() => setShowRunRulesModal(true)}>
            Run rules
          </button>
        }
      />

      {splitTxn && (
        <SplitModal
          transaction={splitTxn}
          categories={categories}
          onClose={() => setSplitTxn(null)}
          onSaved={() => setRefreshKey((k) => k + 1)}
        />
      )}

      {showRunRulesModal && (
        <RunRulesModal
          categories={categories}
          onClose={() => setShowRunRulesModal(false)}
          onApplied={() => {
            setShowRunRulesModal(false);
            setRefreshKey((k) => k + 1);
          }}
        />
      )}
    </div>
  );
}

import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { setCategorizationChangedListener } from "../api/rules";
import { RunRulesModal } from "../components/RunRulesModal";
import { SplitModal } from "../components/SplitModal";
import { TransactionTable } from "../components/TransactionTable";
import { useLedgerData } from "../hooks/useLedgerData";

export function Transactions() {
  const { accounts, categories, loadCategories, splitTxn, setSplitTxn, refreshKey, refresh } = useLedgerData();
  const [showRunRulesModal, setShowRunRulesModal] = useState(false);
  const [searchParams] = useSearchParams();

  // Rules can be added/edited from outside this page too -- the toast-driven learned-rule and
  // conflict-resolution flows (components/Toast.tsx) are mounted at the app root, not here.
  useEffect(() => {
    setCategorizationChangedListener(refresh);
    return () => setCategorizationChangedListener(null);
  }, [refresh]);

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
          onSaved={refresh}
        />
      )}

      {showRunRulesModal && (
        <RunRulesModal
          categories={categories}
          onClose={() => setShowRunRulesModal(false)}
          onApplied={() => {
            setShowRunRulesModal(false);
            refresh();
          }}
        />
      )}
    </div>
  );
}

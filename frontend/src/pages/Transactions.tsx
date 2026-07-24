import { useEffect, useState } from "react";
import { accountsApi } from "../api/accounts";
import { categoriesApi } from "../api/categories";
import type { Account, Category, Transaction } from "../api/types";
import { SplitModal } from "../components/SplitModal";
import { TransactionTable } from "../components/TransactionTable";

export function Transactions() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [splitTxn, setSplitTxn] = useState<Transaction | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    accountsApi.list().then(setAccounts);
    categoriesApi.list().then(setCategories);
  }, []);

  return (
    <div>
      <h1>Transactions</h1>
      <p className="sub">All accounts. Filter, search, split, and review categorization suggestions.</p>

      <TransactionTable
        categories={categories}
        accounts={accounts}
        onSplitTransaction={setSplitTxn}
        refreshKey={refreshKey}
      />

      {splitTxn && (
        <SplitModal
          transaction={splitTxn}
          categories={categories}
          onClose={() => setSplitTxn(null)}
          onSaved={() => setRefreshKey((k) => k + 1)}
        />
      )}
    </div>
  );
}

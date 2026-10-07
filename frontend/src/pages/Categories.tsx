import { useEffect, useState } from "react";
import { accountsApi } from "../api/accounts";
import { activeCategories, categoriesApi, flattenAllCategories } from "../api/categories";
import type { Account, Category, Transaction } from "../api/types";
import { CategoryCombobox } from "../components/CategoryCombobox";
import { SplitModal } from "../components/SplitModal";
import { TransactionTable } from "../components/TransactionTable";

// Same starting window as the Accounts screen: the current calendar year.
const ACCOUNTING_PERIOD_START = `${new Date().getFullYear()}-01-01`;

// The last category picked here, so the screen reopens on it.
const CATEGORY_STORAGE_KEY = "budgeter.categories.selected";

export function Categories() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [categories, setCategories] = useState<Category[] | null>(null);
  const [currentCategoryId, setCurrentCategoryId] = useState<number | null>(() => {
    const stored = Number(localStorage.getItem(CATEGORY_STORAGE_KEY));
    return Number.isInteger(stored) && stored > 0 ? stored : null;
  });
  const [splitTxn, setSplitTxn] = useState<Transaction | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  function loadCategories() {
    // include_archived so historical transactions keep rendering their
    // (possibly archived) category; pickers filter to active internally.
    categoriesApi.list(true).then(setCategories);
  }

  useEffect(() => {
    accountsApi.list().then(setAccounts);
    loadCategories();
  }, []);

  function selectCategory(categoryId: number | null) {
    setCurrentCategoryId(categoryId);
    if (categoryId === null) localStorage.removeItem(CATEGORY_STORAGE_KEY);
    else localStorage.setItem(CATEGORY_STORAGE_KEY, String(categoryId));
  }

  const tree = categories ?? [];
  // A remembered category may have been deleted since; treat it as unpicked.
  const selectedId =
    categories !== null && flattenAllCategories(tree).some((c) => c.id === currentCategoryId)
      ? currentCategoryId
      : null;

  return (
    <div>
      <h1>Categories</h1>
      <p className="sub">
        Pick a category below — the transaction list is pre-filtered to it. A parent category includes
        everything beneath it.
      </p>

      {categories !== null && (
        <div style={{ maxWidth: 360, marginBottom: 18 }}>
          <CategoryCombobox
            categories={activeCategories(tree)}
            value={selectedId}
            onChange={selectCategory}
            mode="filter"
            placeholder="Choose a category…"
          />
        </div>
      )}

      {selectedId !== null && (
        <TransactionTable
          key={selectedId}
          categories={tree}
          accounts={accounts}
          lockCategoryId={selectedId}
          onSplitTransaction={setSplitTxn}
          refreshKey={refreshKey}
          onCategoriesChanged={loadCategories}
          initialFilters={{ date_from: ACCOUNTING_PERIOD_START }}
        />
      )}

      {splitTxn && (
        <SplitModal
          transaction={splitTxn}
          categories={tree}
          onClose={() => setSplitTxn(null)}
          onSaved={() => setRefreshKey((k) => k + 1)}
        />
      )}
    </div>
  );
}

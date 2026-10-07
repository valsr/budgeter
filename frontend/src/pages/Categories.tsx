import { useState } from "react";
import { activeCategories, flattenAllCategories } from "../api/categories";
import { useUserStorage } from "../auth/userStorage";
import { CategoryCombobox } from "../components/CategoryCombobox";
import { SplitModal } from "../components/SplitModal";
import { TransactionTable } from "../components/TransactionTable";
import { useLedgerData } from "../hooks/useLedgerData";

// Same starting window as the Accounts screen: the current calendar year.
const ACCOUNTING_PERIOD_START = `${new Date().getFullYear()}-01-01`;

// The last category picked here, so the screen reopens on it.
const CATEGORY_STORAGE_KEY = "categories.selected";

export function Categories() {
  const storage = useUserStorage();
  const { accounts, categories: tree, categoriesLoaded, loadCategories, splitTxn, setSplitTxn, refreshKey, refresh } =
    useLedgerData();
  const [currentCategoryId, setCurrentCategoryId] = useState<number | null>(() => {
    const stored = Number(storage.get(CATEGORY_STORAGE_KEY));
    return Number.isInteger(stored) && stored > 0 ? stored : null;
  });

  function selectCategory(categoryId: number | null) {
    setCurrentCategoryId(categoryId);
    if (categoryId === null) storage.remove(CATEGORY_STORAGE_KEY);
    else storage.set(CATEGORY_STORAGE_KEY, String(categoryId));
  }

  // A remembered category may have been deleted since; treat it as unpicked.
  const selectedId =
    categoriesLoaded && flattenAllCategories(tree).some((c) => c.id === currentCategoryId)
      ? currentCategoryId
      : null;

  return (
    <div>
      <h1>Categories</h1>
      <p className="sub">
        Pick a category below — the transaction list is pre-filtered to it. A parent category includes
        everything beneath it.
      </p>

      {categoriesLoaded && (
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
          onSaved={refresh}
        />
      )}
    </div>
  );
}

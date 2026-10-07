import { useCallback, useEffect, useState } from "react";
import { accountsApi } from "../api/accounts";
import { categoriesApi } from "../api/categories";
import type { Account, Category, Transaction } from "../api/types";

/** What every screen built around a TransactionTable needs: the accounts, the full category tree,
 * the transaction being split, and a key to bump when the list should refetch. */
export function useLedgerData() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  // null until first loaded, for screens that must tell "none yet" from "none".
  const [categories, setCategories] = useState<Category[] | null>(null);
  const [splitTxn, setSplitTxn] = useState<Transaction | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const loadAccounts = useCallback(() => accountsApi.list().then(setAccounts), []);
  // include_archived, so historical transactions keep rendering their category.
  const loadCategories = useCallback(() => categoriesApi.list(true).then(setCategories), []);
  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  useEffect(() => {
    loadAccounts();
    loadCategories();
  }, [loadAccounts, loadCategories]);

  return {
    accounts,
    categories: categories ?? [],
    categoriesLoaded: categories !== null,
    loadAccounts,
    loadCategories,
    splitTxn,
    setSplitTxn,
    refreshKey,
    refresh,
  };
}

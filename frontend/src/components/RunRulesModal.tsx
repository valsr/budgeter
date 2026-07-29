import { useEffect, useMemo, useState } from "react";
import { accountsApi } from "../api/accounts";
import { flattenAllCategories } from "../api/categories";
import { rulesApi } from "../api/rules";
import type { Account, Category, RunPreviewItem } from "../api/types";
import { CategoryTag, hexToRgba } from "./CategoryTag";
import { Modal } from "./Modal";

const DEFAULT_ACCOUNT_COLOR = "#4f8a9c";

interface RunRulesModalProps {
  categories: Category[];
  onClose: () => void;
  onApplied: (count: number) => void;
}

export function RunRulesModal({ categories, onClose, onApplied }: RunRulesModalProps) {
  const [items, setItems] = useState<RunPreviewItem[] | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [removedIds, setRemovedIds] = useState<Set<number>>(new Set());
  const [applying, setApplying] = useState(false);

  useEffect(() => {
    rulesApi.runPreview().then((res) => setItems(res.items));
    accountsApi.list().then(setAccounts);
  }, []);

  const categoryById = useMemo(() => {
    const map = new Map<number, { path: string; color: string }>();
    for (const opt of flattenAllCategories(categories)) {
      map.set(opt.id, { path: opt.path, color: opt.color });
    }
    return map;
  }, [categories]);
  const accountById = useMemo(() => new Map(accounts.map((a) => [a.id, a])), [accounts]);

  const visible = (items ?? []).filter((i) => !removedIds.has(i.transaction_id));

  function remove(transactionId: number) {
    setRemovedIds((prev) => new Set(prev).add(transactionId));
  }

  async function apply() {
    setApplying(true);
    try {
      await rulesApi.recategorize(visible.map((i) => i.transaction_id));
      onApplied(visible.length);
    } finally {
      setApplying(false);
    }
  }

  return (
    <Modal
      title="Run categorization rules"
      onClose={onClose}
      onSubmit={items !== null && visible.length > 0 ? apply : undefined}
      submitLabel={applying ? "Applying…" : `Apply ${visible.length} change${visible.length === 1 ? "" : "s"}`}
      submitDisabled={applying}
      wide
    >
      {items === null && <p className="sub">Checking uncategorized transactions against your rules…</p>}
      {items !== null && items.length === 0 && (
        <p className="sub">No uncategorized transactions match your current rules.</p>
      )}
      {items !== null && items.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Name</th>
              <th>Account</th>
              <th>New category</th>
              <th className="right">Deposit</th>
              <th className="right">Withdraw</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {visible.map((item) => {
              const account = accountById.get(item.account_id);
              const accountColor = account?.color ?? DEFAULT_ACCOUNT_COLOR;
              const cat = categoryById.get(item.category_id);
              return (
                <tr key={item.transaction_id}>
                  <td>{item.date}</td>
                  <td>{item.name}</td>
                  <td>
                    {account && (
                      <span
                        className="tag"
                        style={{ background: hexToRgba(accountColor, 0.15), color: accountColor }}
                      >
                        {account.name}
                      </span>
                    )}
                  </td>
                  <td>{cat ? <CategoryTag label={cat.path} color={cat.color} /> : item.category_id}</td>
                  <td className="right">{item.amount > 0 ? `$${item.amount.toFixed(2)}` : "—"}</td>
                  <td className="right">{item.amount < 0 ? `$${Math.abs(item.amount).toFixed(2)}` : "—"}</td>
                  <td className="ctrl-cell">
                    <span
                      className="icon-btn remove"
                      title="Remove from this categorization run"
                      onClick={() => remove(item.transaction_id)}
                    >
                      🗑
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Modal>
  );
}

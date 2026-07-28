import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useState } from "react";
import { categoriesApi } from "../api/categories";
import { rulesApi } from "../api/rules";
import type { Category, ConditionField, ConditionOperator, MatchType, Rule } from "../api/types";
import { RuleModal } from "./RuleModal";

interface ConflictToast {
  id: string;
  kind: "conflict";
  ruleId: number;
  ruleSummary: string;
}

interface SuggestionToast {
  id: string;
  kind: "suggestion";
  tier: number;
  matchType: MatchType;
  conditions: { field: ConditionField; operator: ConditionOperator; value: string }[];
  targetCategoryId: number;
}

type ToastItem = ConflictToast | SuggestionToast;

type ModalState = null | { kind: "edit-rule" } | { kind: "learned-rule"; toast: SuggestionToast };

interface ToastContextValue {
  push: (item: Omit<ConflictToast, "id"> | Omit<SuggestionToast, "id">) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let nextToastId = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [modalState, setModalState] = useState<ModalState>(null);
  const [categories, setCategories] = useState<Category[] | null>(null);
  const [editingRule, setEditingRule] = useState<Rule | null>(null);

  function dismiss(id: string) {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }

  function push(item: Omit<ConflictToast, "id"> | Omit<SuggestionToast, "id">) {
    setToasts((prev) => [...prev, { ...item, id: String(nextToastId++) } as ToastItem]);
  }

  async function ensureCategories(): Promise<Category[]> {
    if (categories) return categories;
    const list = await categoriesApi.list();
    setCategories(list);
    return list;
  }

  async function openConflictRule(toast: ConflictToast) {
    const [rule] = await Promise.all([rulesApi.get(toast.ruleId), ensureCategories()]);
    setEditingRule(rule);
    setModalState({ kind: "edit-rule" });
    dismiss(toast.id);
  }

  async function openLearnedRule(toast: SuggestionToast) {
    await ensureCategories();
    setModalState({ kind: "learned-rule", toast });
    dismiss(toast.id);
  }

  function closeModal() {
    setModalState(null);
    setEditingRule(null);
  }

  return (
    <ToastContext.Provider value={{ push }}>
      {children}
      <div className="toast-stack">
        {toasts.map((t) =>
          t.kind === "conflict" ? (
            <div className="toast" key={t.id}>
              <span>
                Rule already categorizes matching transactions as something else ({t.ruleSummary}).{" "}
                <span className="toast-link" onClick={() => openConflictRule(t)}>
                  View rule
                </span>
              </span>
              <span className="toast-close" onClick={() => dismiss(t.id)}>
                ✕
              </span>
            </div>
          ) : (
            <div className="toast" key={t.id}>
              <span>
                Possible rule found: {t.conditions.map((c) => `${c.field} ${c.operator} "${c.value}"`).join(" and ")}
              </span>
              <span className="toast-action" onClick={() => openLearnedRule(t)}>
                Add
              </span>
              <span className="toast-close" onClick={() => dismiss(t.id)}>
                ✕
              </span>
            </div>
          ),
        )}
      </div>

      {modalState?.kind === "edit-rule" && editingRule && categories && (
        <RuleModal mode="edit" rule={editingRule} categories={categories} onClose={closeModal} onSaved={closeModal} />
      )}
      {modalState?.kind === "learned-rule" && categories && (
        <RuleModal
          mode="new"
          categories={categories}
          learnedFlow
          initial={{
            matchType: modalState.toast.matchType,
            conditions: modalState.toast.conditions,
            targetCategoryId: modalState.toast.targetCategoryId,
          }}
          onClose={closeModal}
          onSaved={closeModal}
        />
      )}
    </ToastContext.Provider>
  );
}

/** Call after a manual, single-split category assignment. Fires the
 * server-side learning check and surfaces a toast if there's a rule
 * conflict or a proposed new rule; no-ops silently otherwise. */
export function useLearnCheck() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useLearnCheck must be used within a ToastProvider");

  return useCallback(
    async (transactionId: number) => {
      const res = await rulesApi.learnCheck(transactionId);
      if (res.status === "conflict" && res.conflict) {
        ctx.push({ kind: "conflict", ruleId: res.conflict.rule_id, ruleSummary: res.conflict.rule_summary });
      } else if (res.status === "suggestion" && res.suggestion) {
        ctx.push({
          kind: "suggestion",
          tier: res.suggestion.tier,
          matchType: res.suggestion.match_type,
          conditions: res.suggestion.conditions,
          targetCategoryId: res.suggestion.target_category_id,
        });
      }
    },
    [ctx],
  );
}

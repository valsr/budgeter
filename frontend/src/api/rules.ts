import { apiFetch } from "./client";
import type {
  ConditionField,
  ConditionOperator,
  LearnCheckResponse,
  LearnRuleResponse,
  MatchType,
  PreviewMatchesResponse,
  Rule,
  RunPreviewResponse,
} from "./types";

export interface ConditionInput {
  field: ConditionField;
  operator: ConditionOperator;
  value: string;
}

export interface RuleInput {
  match_type: MatchType;
  conditions: ConditionInput[];
  target_category_id: number;
}

type CategorizationChangedListener = () => void;
let categorizationChangedListener: CategorizationChangedListener | null = null;

/** Subscribe to be told whenever a rule is created/edited/learned -- each
 * of those immediately re-runs categorization against every currently-
 * uncategorized transaction server-side (docs/requirements.md §3.1), so a
 * transaction list already on screen (e.g. the Transactions page) can go
 * stale without the page itself doing anything. Rule creation/editing can
 * happen from outside that page's component tree (the toast-driven learned-
 * rule/conflict flows in components/Toast.tsx are mounted at the app root),
 * so a prop callback can't reach it -- this fills that gap. Only one
 * subscriber at a time; pass `null` to unsubscribe. */
export function setCategorizationChangedListener(listener: CategorizationChangedListener | null): void {
  categorizationChangedListener = listener;
}

function notifyCategorizationChanged(): void {
  categorizationChangedListener?.();
}

export const rulesApi = {
  list: () => apiFetch<Rule[]>("/api/rules"),
  get: (id: number) => apiFetch<Rule>(`/api/rules/${id}`),
  create: (input: RuleInput) =>
    apiFetch<Rule>("/api/rules", { method: "POST", body: JSON.stringify(input) }).then((rule) => {
      notifyCategorizationChanged();
      return rule;
    }),
  update: (id: number, input: Partial<RuleInput>) =>
    apiFetch<Rule>(`/api/rules/${id}`, { method: "PATCH", body: JSON.stringify(input) }).then((rule) => {
      notifyCategorizationChanged();
      return rule;
    }),
  remove: (id: number) => apiFetch<void>(`/api/rules/${id}`, { method: "DELETE" }),
  reorder: (ordered_ids: number[]) =>
    apiFetch<Rule[]>("/api/rules/reorder", { method: "POST", body: JSON.stringify({ ordered_ids }) }),
  recategorize: (transactionIds: number[] | null = null) =>
    apiFetch<{ suggested_count: number }>("/api/rules/recategorize", {
      method: "POST",
      body: JSON.stringify({ transaction_ids: transactionIds }),
    }),
  learnCheck: (transactionId: number) =>
    apiFetch<LearnCheckResponse>("/api/rules/learn-check", {
      method: "POST",
      body: JSON.stringify({ transaction_id: transactionId }),
    }),
  previewMatches: (input: RuleInput) =>
    // silent: fires on every debounced keystroke while editing a rule, so a
    // transient 422 (mid-typing, incomplete condition) shouldn't toast.
    apiFetch<PreviewMatchesResponse>(
      "/api/rules/preview-matches",
      { method: "POST", body: JSON.stringify(input) },
      { silent: true },
    ),
  learn: (input: RuleInput) =>
    apiFetch<LearnRuleResponse>("/api/rules/learn", { method: "POST", body: JSON.stringify(input) }).then((res) => {
      notifyCategorizationChanged();
      return res;
    }),
  runPreview: () => apiFetch<RunPreviewResponse>("/api/rules/run-preview"),
};

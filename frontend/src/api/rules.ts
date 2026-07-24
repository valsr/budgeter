import { apiFetch } from "./client";
import type { ConditionField, ConditionOperator, MatchType, Rule, RuleSuggestion } from "./types";

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

export const rulesApi = {
  list: () => apiFetch<Rule[]>("/api/rules"),
  create: (input: RuleInput) =>
    apiFetch<Rule>("/api/rules", { method: "POST", body: JSON.stringify(input) }),
  update: (id: number, input: Partial<RuleInput>) =>
    apiFetch<Rule>(`/api/rules/${id}`, { method: "PATCH", body: JSON.stringify(input) }),
  remove: (id: number) => apiFetch<void>(`/api/rules/${id}`, { method: "DELETE" }),
  reorder: (ordered_ids: number[]) =>
    apiFetch<Rule[]>("/api/rules/reorder", { method: "POST", body: JSON.stringify({ ordered_ids }) }),
  suggestions: (threshold?: number) =>
    apiFetch<RuleSuggestion[]>(`/api/rules/suggestions${threshold ? `?threshold=${threshold}` : ""}`),
  recategorize: (transactionIds: number[] | null = null) =>
    apiFetch<{ suggested_count: number }>("/api/rules/recategorize", {
      method: "POST",
      body: JSON.stringify({ transaction_ids: transactionIds }),
    }),
};

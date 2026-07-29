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

export const rulesApi = {
  list: () => apiFetch<Rule[]>("/api/rules"),
  get: (id: number) => apiFetch<Rule>(`/api/rules/${id}`),
  create: (input: RuleInput) =>
    apiFetch<Rule>("/api/rules", { method: "POST", body: JSON.stringify(input) }),
  update: (id: number, input: Partial<RuleInput>) =>
    apiFetch<Rule>(`/api/rules/${id}`, { method: "PATCH", body: JSON.stringify(input) }),
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
    apiFetch<LearnRuleResponse>("/api/rules/learn", { method: "POST", body: JSON.stringify(input) }),
  runPreview: () => apiFetch<RunPreviewResponse>("/api/rules/run-preview"),
};

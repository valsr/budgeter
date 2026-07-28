export type AccountType = "asset" | "liability";

export interface Account {
  id: number;
  name: string;
  account_number: string | null;
  type: AccountType;
  opening_balance: number;
  color: string | null;
  balance: number;
}

export interface Category {
  id: number;
  name: string;
  parent_id: number | null;
  color: string;
  sort_order: number;
  archived_at: string | null;
  children: Category[];
}

export type SuggestionSource = "rule" | "ai";

export interface Split {
  id: number;
  category_id: number | null;
  amount: number;
  suggested_category_id: number | null;
  suggestion_source: SuggestionSource | null;
}

export type TransactionType = "normal" | "transfer";

export interface Transaction {
  id: number;
  account_id: number;
  date: string;
  name: string;
  type: TransactionType;
  transfer_pair_id: number | null;
  splits: Split[];
}

export interface TransactionPage {
  items: Transaction[];
  total: number;
  page: number;
  page_size: number;
}

export type ConditionField = "date" | "day_of_month" | "name" | "account" | "amount";
export type ConditionOperator = "contains" | "not_contains" | "equals" | "less_than" | "greater_than";
export type MatchType = "any" | "all";

export interface RuleCondition {
  id: number;
  field: ConditionField;
  operator: ConditionOperator;
  value: string;
}

export interface Rule {
  id: number;
  match_type: MatchType;
  priority: number;
  target_category_id: number;
  conditions: RuleCondition[];
}

export interface RuleConflictInfo {
  rule_id: number;
  rule_summary: string;
  matched_category_id: number;
  assigned_category_id: number;
}

export interface LearnedRuleSuggestion {
  tier: number;
  match_type: MatchType;
  conditions: { field: ConditionField; operator: ConditionOperator; value: string }[];
  target_category_id: number;
}

export type LearnCheckStatus = "covered" | "conflict" | "suggestion" | "none";

export interface LearnCheckResponse {
  status: LearnCheckStatus;
  conflict: RuleConflictInfo | null;
  suggestion: LearnedRuleSuggestion | null;
}

export interface PreviewMatchSample {
  id: number;
  date: string;
  name: string;
  amount: number;
}

export interface PreviewMatchesResponse {
  count: number;
  sample: PreviewMatchSample[];
}

export interface LearnRuleResponse {
  rule: Rule;
  confirmed_count: number;
  confirmed_transaction_ids: number[];
}

export interface ImportBatch {
  id: number;
  filename: string;
  account_id: number;
  imported_at: string;
  row_count: number;
  imported_count: number;
  skipped_duplicate_count: number;
  needs_review_count: number;
}

export type ReviewItemStatus = "pending" | "resolved_new" | "resolved_merged" | "resolved_skipped";

export interface ReviewQueueItem {
  id: number;
  import_batch_id: number;
  account_id: number;
  date: string;
  amount: number;
  name: string;
  candidate_transaction_id: number | null;
  status: ReviewItemStatus;
}

export interface BudgetAmount {
  year: number;
  month: number;
  amount: number;
}

export interface BudgetCategory {
  category_id: number;
  amounts: BudgetAmount[];
}

export interface Budget {
  id: number;
  name: string;
  budget_categories: BudgetCategory[];
}

export interface MonthCell {
  budgeted: number;
  actual: number;
}

export interface ReportRow {
  category_id: number;
  name: string;
  is_parent: boolean;
  monthly: Record<number, MonthCell>;
  ytd_diff: number;
  has_budget: boolean;
}

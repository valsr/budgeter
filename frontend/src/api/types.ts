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
  is_income: boolean;
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

export interface PreviewMatchItem {
  id: number;
  date: string;
  name: string;
  amount: number;
}

export interface PreviewMatchesResponse {
  count: number;
  matches: PreviewMatchItem[];
}

export interface LearnRuleResponse {
  rule: Rule;
  confirmed_count: number;
  confirmed_transaction_ids: number[];
}

export interface RunPreviewItem {
  transaction_id: number;
  date: string;
  name: string;
  account_id: number;
  category_id: number;
  amount: number;
}

export interface RunPreviewResponse {
  items: RunPreviewItem[];
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

export interface DetectedAccount {
  parsed_name: string | null;
  transaction_count: number;
  matched_account_id: number | null;
  suggested_type: AccountType | null;
}

export interface DetectAccountsResponse {
  has_account_sections: boolean;
  accounts: DetectedAccount[];
}

export interface NewAccountInput {
  name: string;
  type: AccountType;
  account_number?: string | null;
  opening_balance?: number;
  color?: string | null;
}

export interface ImportResolutionInput {
  parsed_name: string | null;
  account_id?: number;
  new_account?: NewAccountInput;
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
  depth: number;
  is_income: boolean;
}

export type ChangeOperation = "create" | "update" | "delete";
export type ChangeEntityType = "account" | "category" | "transaction";

export interface ChangeItem {
  entity_id: number;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}

export interface ChangeGroup {
  group_id: string;
  entity_type: ChangeEntityType;
  operation: ChangeOperation;
  summary: string;
  created_at: string;
  undone_at: string | null;
  is_stale: boolean;
  items: ChangeItem[];
}

export interface HistoryPage {
  items: ChangeGroup[];
  total: number;
  page: number;
  page_size: number;
}

export interface UndoResult {
  group_id: string;
  status: "undone" | "skipped";
  reason: string | null;
}

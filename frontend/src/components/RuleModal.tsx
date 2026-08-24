import { useEffect, useState } from "react";
import { accountsApi } from "../api/accounts";
import { flattenLeafCategories } from "../api/categories";
import { rulesApi } from "../api/rules";
import type {
  Account,
  Category,
  ConditionField,
  ConditionOperator,
  MatchType,
  PreviewMatchItem,
  Rule,
} from "../api/types";
import { Modal } from "./Modal";

// 20% wider than the default 460px modal -- the condition row (two selects
// plus a value input) clips against the edge at the default width.
const MODAL_WIDTH = 552;
const PREVIEW_PAGE_SIZE = 10;

const FIELD_OPTIONS: { value: ConditionField; label: string }[] = [
  { value: "name", label: "Name" },
  { value: "amount", label: "Amount" },
  { value: "account", label: "Account" },
  { value: "day_of_month", label: "Day of month" },
  { value: "date", label: "Date" },
];
const OPERATOR_OPTIONS: { value: ConditionOperator; label: string }[] = [
  { value: "contains", label: "contains" },
  { value: "not_contains", label: "does not contain" },
  { value: "equals", label: "equals" },
  { value: "less_than", label: "less than" },
  { value: "greater_than", label: "greater than" },
];
// Amount-only: direction operators ignore the value entirely (any deposit,
// any withdrawal, regardless of size), so they're additive to the base set
// rather than a replacement for it -- equals/less_than/greater_than above
// still compare magnitude (rule_engine's AMOUNT field is abs()'d).
const AMOUNT_OPERATOR_OPTIONS: { value: ConditionOperator; label: string }[] = [
  ...OPERATOR_OPTIONS,
  { value: "is_deposit", label: "is a deposit/credit" },
  { value: "is_withdrawal", label: "is a withdrawal/debit" },
];
// Account-only: the condition's value is an account *id* (rule_engine
// compares TransactionContext.account_id), so the only operator with a
// sensible meaning is equality -- substring and ordering comparisons on a
// surrogate key are nonsense, and the coercion behind them (int(value))
// rejects anything but a bare id.
const ACCOUNT_OPERATOR_OPTIONS: { value: ConditionOperator; label: string }[] = [
  { value: "equals", label: "is" },
];
const DIRECTION_OPERATORS: ConditionOperator[] = ["is_deposit", "is_withdrawal"];
function operatorOptionsFor(field: ConditionField) {
  if (field === "amount") return AMOUNT_OPERATOR_OPTIONS;
  if (field === "account") return ACCOUNT_OPERATOR_OPTIONS;
  return OPERATOR_OPTIONS;
}
function operatorNeedsValue(operator: ConditionOperator) {
  return !DIRECTION_OPERATORS.includes(operator);
}

interface RuleConditionInput {
  field: ConditionField;
  operator: ConditionOperator;
  value: string;
}

/** Pull a loaded condition onto an operator this editor still offers for its
 * field -- older account conditions may carry a `contains`/`less_than`
 * operator that only ever compared account ids by accident. */
function normalizeCondition(c: RuleConditionInput): RuleConditionInput {
  const valid = operatorOptionsFor(c.field).map((o) => o.value);
  return valid.includes(c.operator) ? c : { ...c, operator: valid[0] };
}

interface RuleModalProps {
  mode: "new" | "edit";
  rule?: Rule;
  categories: Category[];
  onClose: () => void;
  onSaved: () => void;
  /** Pre-fill for a rule the learning engine proposed. */
  initial?: {
    matchType: MatchType;
    conditions: RuleConditionInput[];
    targetCategoryId: number;
  };
  /** When true, saving does a one-time auto-confirm backfill (POST /api/rules/learn)
   * instead of the normal suggest-only create/update flow. */
  learnedFlow?: boolean;
  /** The rules being combined into this one, when opened from the "Merge rules"
   * flow (mode is always "new" in that case). Once the merged rule is created,
   * these are deleted so the merge is a clean replacement rather than leaving
   * redundant originals behind. */
  mergeSourceRules?: Rule[];
}

export function RuleModal({ mode, rule, categories, onClose, onSaved, initial, learnedFlow, mergeSourceRules }: RuleModalProps) {
  const [matchType, setMatchType] = useState<MatchType>(rule?.match_type ?? initial?.matchType ?? "all");
  const [conditions, setConditions] = useState<RuleConditionInput[]>(
    (
      rule?.conditions.map((c) => ({ field: c.field, operator: c.operator, value: c.value })) ??
      initial?.conditions ?? [{ field: "name", operator: "contains", value: "" }]
    ).map(normalizeCondition),
  );
  const leafOptions = flattenLeafCategories(categories);
  const [targetCategoryId, setTargetCategoryId] = useState<number | "">(
    rule?.target_category_id ?? initial?.targetCategoryId ?? leafOptions[0]?.id ?? "",
  );
  const [preview, setPreview] = useState<{ count: number; matches: PreviewMatchItem[] } | null>(null);
  const [previewPage, setPreviewPage] = useState(1);
  // An `account` condition's value is an account id, so the picker needs the
  // account list to turn that into something choosable and readable.
  const [accounts, setAccounts] = useState<Account[]>([]);

  useEffect(() => {
    accountsApi.list().then(setAccounts);
  }, []);

  function updateCondition(i: number, patch: Partial<RuleConditionInput>) {
    setConditions((prev) => prev.map((c, idx) => (idx === i ? { ...c, ...patch } : c)));
  }

  useEffect(() => {
    if (
      targetCategoryId === "" ||
      conditions.some((c) => operatorNeedsValue(c.operator) && c.value.trim() === "")
    ) {
      setPreview(null);
      return;
    }
    const handle = setTimeout(() => {
      rulesApi
        .previewMatches({ match_type: matchType, conditions, target_category_id: targetCategoryId })
        .then((res) => {
          setPreview(res);
          setPreviewPage(1);
        })
        .catch(() => setPreview(null));
    }, 400);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matchType, JSON.stringify(conditions), targetCategoryId]);

  const previewTotalPages = preview ? Math.max(1, Math.ceil(preview.matches.length / PREVIEW_PAGE_SIZE)) : 1;
  const previewPageItems = preview
    ? preview.matches.slice((previewPage - 1) * PREVIEW_PAGE_SIZE, previewPage * PREVIEW_PAGE_SIZE)
    : [];

  const incomplete =
    targetCategoryId === "" ||
    conditions.some((c) => operatorNeedsValue(c.operator) && c.value.trim() === "");

  async function save() {
    if (incomplete) return;
    const payload = { match_type: matchType, conditions, target_category_id: targetCategoryId };
    if (learnedFlow) {
      await rulesApi.learn(payload);
    } else if (mode === "new") {
      await rulesApi.create(payload);
      if (mergeSourceRules) {
        await Promise.all(mergeSourceRules.map((r) => rulesApi.remove(r.id)));
      }
    } else if (rule) {
      await rulesApi.update(rule.id, payload);
    }
    onSaved();
  }

  const title = mergeSourceRules
    ? `Merge ${mergeSourceRules.length} rules`
    : mode === "edit"
      ? "Edit rule"
      : learnedFlow
        ? "Add learned rule"
        : "New rule";

  return (
    <Modal
      title={title}
      onClose={onClose}
      onSubmit={save}
      submitLabel={mergeSourceRules ? "Create merged rule" : learnedFlow ? "Add rule" : "Save rule"}
      submitDisabled={incomplete}
      width={MODAL_WIDTH}
    >
      {mergeSourceRules && (
        <p className="sub" style={{ marginBottom: 12 }}>
          Combines the conditions of the {mergeSourceRules.length} selected rules with ANY matching. Creating this
          rule deletes those {mergeSourceRules.length} originals.
        </p>
      )}
      <div className="field">
        <label>Match</label>
        <select value={matchType} onChange={(e) => setMatchType(e.target.value as MatchType)}>
          <option value="all">ALL of the following</option>
          <option value="any">ANY of the following</option>
        </select>
      </div>
      {conditions.map((c, i) => (
        <div className="cond-row" key={i}>
          <select
            value={c.field}
            onChange={(e) => {
              const field = e.target.value as ConditionField;
              const validOperators = operatorOptionsFor(field).map((o) => o.value);
              // Direction operators (is_deposit/is_withdrawal) only make
              // sense for the amount field -- switching away from it falls
              // back to the first still-valid operator instead of keeping
              // a now-meaningless one selected.
              const operator = validOperators.includes(c.operator) ? c.operator : validOperators[0];
              // Switching into or out of `account` changes what the value
              // means (an account id vs. free text), so carrying the old one
              // over would leave an id showing as a name, or a name that
              // fails the server's int() coercion. Default a new account
              // condition to the first account instead of an empty pick.
              const switchesValueKind = (field === "account") !== (c.field === "account");
              const value = switchesValueKind
                ? field === "account"
                  ? String(accounts[0]?.id ?? "")
                  : ""
                : c.value;
              updateCondition(i, { field, operator, value: operatorNeedsValue(operator) ? value : "" });
            }}
          >
            {FIELD_OPTIONS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
          <select
            value={c.operator}
            onChange={(e) => {
              const operator = e.target.value as ConditionOperator;
              updateCondition(i, { operator, value: operatorNeedsValue(operator) ? c.value : "" });
            }}
          >
            {operatorOptionsFor(c.field).map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          {c.field === "account" ? (
            <select
              aria-label="Account"
              style={{ flex: 1 }}
              value={c.value}
              onChange={(e) => updateCondition(i, { value: e.target.value })}
            >
              <option value="" disabled>
                Select an account
              </option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          ) : operatorNeedsValue(c.operator) ? (
            <input
              placeholder="value"
              style={{ flex: 1 }}
              value={c.value}
              onChange={(e) => updateCondition(i, { value: e.target.value })}
            />
          ) : (
            <span className="sub" style={{ flex: 1 }}>
              matches any amount
            </span>
          )}
          {conditions.length > 1 && (
            <span
              className="icon-btn remove"
              onClick={() => setConditions((prev) => prev.filter((_, idx) => idx !== i))}
            >
              🗑
            </span>
          )}
        </div>
      ))}
      <button
        type="button"
        className="btn ghost sm"
        onClick={() => setConditions((prev) => [...prev, { field: "name", operator: "contains", value: "" }])}
      >
        + Add condition
      </button>
      <div className="field" style={{ marginTop: 14 }}>
        <label>Assign category</label>
        <select value={targetCategoryId} onChange={(e) => setTargetCategoryId(Number(e.target.value))}>
          {leafOptions.map((o) => (
            <option key={o.id} value={o.id}>
              {o.path}
            </option>
          ))}
        </select>
      </div>
      {preview && (
        <div style={{ marginTop: 10 }}>
          <p className="sub" style={{ marginBottom: 6 }}>
            {learnedFlow ? "Will categorize" : "Matches"} {preview.count} currently-uncategorized transaction
            {preview.count === 1 ? "" : "s"}
          </p>
          {preview.matches.length > 0 && (
            <>
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Name</th>
                    <th className="right">Deposit</th>
                    <th className="right">Withdraw</th>
                  </tr>
                </thead>
                <tbody>
                  {previewPageItems.map((m) => (
                    <tr key={m.id}>
                      <td>{m.date}</td>
                      <td>{m.name}</td>
                      <td className="right">{m.amount > 0 ? `$${m.amount.toFixed(2)}` : "—"}</td>
                      <td className="right">{m.amount < 0 ? `$${Math.abs(m.amount).toFixed(2)}` : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="pagination">
                <span>
                  Showing {(previewPage - 1) * PREVIEW_PAGE_SIZE + 1}–
                  {Math.min(previewPage * PREVIEW_PAGE_SIZE, preview.matches.length)} of {preview.matches.length}
                </span>
                <div className="pages">
                  <span onClick={() => setPreviewPage((p) => Math.max(1, p - 1))}>‹</span>
                  <span className="cur">{previewPage}</span>
                  {previewTotalPages > 1 && <span>of {previewTotalPages}</span>}
                  <span onClick={() => setPreviewPage((p) => Math.min(previewTotalPages, p + 1))}>›</span>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </Modal>
  );
}

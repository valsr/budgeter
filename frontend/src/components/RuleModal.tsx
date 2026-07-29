import { useEffect, useState } from "react";
import { flattenLeafCategories } from "../api/categories";
import { rulesApi } from "../api/rules";
import type { Category, ConditionField, ConditionOperator, MatchType, PreviewMatchItem, Rule } from "../api/types";
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

interface RuleConditionInput {
  field: ConditionField;
  operator: ConditionOperator;
  value: string;
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
}

export function RuleModal({ mode, rule, categories, onClose, onSaved, initial, learnedFlow }: RuleModalProps) {
  const [matchType, setMatchType] = useState<MatchType>(rule?.match_type ?? initial?.matchType ?? "all");
  const [conditions, setConditions] = useState<RuleConditionInput[]>(
    rule?.conditions.map((c) => ({ field: c.field, operator: c.operator, value: c.value })) ??
      initial?.conditions ?? [{ field: "name", operator: "contains", value: "" }],
  );
  const leafOptions = flattenLeafCategories(categories);
  const [targetCategoryId, setTargetCategoryId] = useState<number | "">(
    rule?.target_category_id ?? initial?.targetCategoryId ?? leafOptions[0]?.id ?? "",
  );
  const [preview, setPreview] = useState<{ count: number; matches: PreviewMatchItem[] } | null>(null);
  const [previewPage, setPreviewPage] = useState(1);

  function updateCondition(i: number, patch: Partial<RuleConditionInput>) {
    setConditions((prev) => prev.map((c, idx) => (idx === i ? { ...c, ...patch } : c)));
  }

  useEffect(() => {
    if (targetCategoryId === "" || conditions.some((c) => c.value.trim() === "")) {
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

  async function save() {
    if (targetCategoryId === "") return;
    const payload = { match_type: matchType, conditions, target_category_id: targetCategoryId };
    if (learnedFlow) {
      await rulesApi.learn(payload);
    } else if (mode === "new") {
      await rulesApi.create(payload);
    } else if (rule) {
      await rulesApi.update(rule.id, payload);
    }
    onSaved();
  }

  const title = mode === "edit" ? "Edit rule" : learnedFlow ? "Add learned rule" : "New rule";

  return (
    <Modal
      title={title}
      onClose={onClose}
      onSubmit={save}
      submitLabel={learnedFlow ? "Add rule" : "Save rule"}
      width={MODAL_WIDTH}
    >
      <div className="field">
        <label>Match</label>
        <select value={matchType} onChange={(e) => setMatchType(e.target.value as MatchType)}>
          <option value="all">ALL of the following</option>
          <option value="any">ANY of the following</option>
        </select>
      </div>
      {conditions.map((c, i) => (
        <div className="cond-row" key={i}>
          <select value={c.field} onChange={(e) => updateCondition(i, { field: e.target.value as ConditionField })}>
            {FIELD_OPTIONS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
          <select
            value={c.operator}
            onChange={(e) => updateCondition(i, { operator: e.target.value as ConditionOperator })}
          >
            {OPERATOR_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <input
            placeholder="value"
            style={{ flex: 1 }}
            value={c.value}
            onChange={(e) => updateCondition(i, { value: e.target.value })}
          />
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

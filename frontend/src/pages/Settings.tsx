import { useEffect, useState } from "react";
import { accountsApi } from "../api/accounts";
import { backupApi } from "../api/backup";
import { categoriesApi, flattenAllCategories } from "../api/categories";
import { rulesApi } from "../api/rules";
import { settingsApi } from "../api/settings";
import type { Account, Category, ConditionField, ConditionOperator, MatchType, Rule } from "../api/types";
import { useAuth } from "../auth/context";
import { BackupCards } from "../components/BackupCards";
import { Modal } from "../components/Modal";
import { RuleModal } from "../components/RuleModal";
import { RunRulesModal } from "../components/RunRulesModal";
import { AccountTab } from "./settings/AccountTab";
import { ServerTab } from "./settings/ServerTab";
import { UsersTab } from "./settings/UsersTab";

type Tab = "account" | "cats" | "rules" | "backup" | "history" | "users" | "server";

export function Settings() {
  const { user } = useAuth();
  const [tab, setTab] = useState<Tab>("account");

  return (
    <div>
      <h1>Settings</h1>
      <p className="sub">Your account, category taxonomy, categorization rules, and backups.</p>
      <div className="settings-tabs">
        <span className={tab === "account" ? "active" : ""} onClick={() => setTab("account")}>
          Account
        </span>
        <span className={tab === "cats" ? "active" : ""} onClick={() => setTab("cats")}>
          Categories
        </span>
        <span className={tab === "rules" ? "active" : ""} onClick={() => setTab("rules")}>
          Categorization rules
        </span>
        <span className={tab === "backup" ? "active" : ""} onClick={() => setTab("backup")}>
          Backup &amp; restore
        </span>
        <span className={tab === "history" ? "active" : ""} onClick={() => setTab("history")}>
          History
        </span>
        {user.is_admin && (
          <>
            <span className={tab === "users" ? "active" : ""} onClick={() => setTab("users")}>
              Users
            </span>
            <span className={tab === "server" ? "active" : ""} onClick={() => setTab("server")}>
              Server
            </span>
          </>
        )}
      </div>

      {tab === "account" && <AccountTab />}
      {tab === "cats" && <CategoriesTab />}
      {tab === "rules" && <RulesTab />}
      {tab === "backup" && <BackupTab />}
      {tab === "history" && <HistoryRetentionTab />}
      {/* Re-checked here, not just on the tab strip: losing admin while one of these is open closes it. */}
      {tab === "users" && user.is_admin && <UsersTab />}
      {tab === "server" && user.is_admin && <ServerTab />}
    </div>
  );
}

function findCategoryById(tree: Category[], id: number): Category | null {
  for (const node of tree) {
    if (node.id === id) return node;
    const found = findCategoryById(node.children, id);
    if (found) return found;
  }
  return null;
}

interface DragState {
  id: number;
  group: number | "root";
}

function CategoriesTab() {
  const [tree, setTree] = useState<Category[]>([]);
  const [modal, setModal] = useState<null | { mode: "new" | "edit"; category?: Category }>(null);
  const [dragState, setDragState] = useState<DragState | null>(null);

  function load() {
    categoriesApi.list().then(setTree);
  }

  useEffect(load, []);

  async function reorder(group: number | "root", draggedId: number, targetId: number) {
    const siblings = group === "root" ? tree : findCategoryById(tree, group)?.children ?? [];
    const ids = siblings.map((c) => c.id);
    const from = ids.indexOf(draggedId);
    const to = ids.indexOf(targetId);
    if (from < 0 || to < 0) return;
    const reordered = [...ids];
    reordered.splice(from, 1);
    reordered.splice(to, 0, draggedId);
    await categoriesApi.reorder(group === "root" ? null : group, reordered);
    load();
  }

  async function archive(id: number) {
    await categoriesApi.archive(id);
    load();
  }

  return (
    <div>
      <div className="toolbar">
        <span className="sub" style={{ margin: 0 }}>
          Drag <span className="drag">⠿</span> to reorder within a group.
        </span>
        <button className="btn sm" onClick={() => setModal({ mode: "new" })}>
          + New category
        </button>
      </div>
      <div>
        {tree.map((cat) => (
          <CategoryTreeRow
            key={cat.id}
            category={cat}
            depth={0}
            group="root"
            dragState={dragState}
            setDragState={setDragState}
            reorder={reorder}
            onEdit={(category) => setModal({ mode: "edit", category })}
            onArchive={archive}
          />
        ))}
      </div>

      {modal && (
        <CategoryModal
          mode={modal.mode}
          category={modal.category}
          tree={tree}
          onClose={() => setModal(null)}
          onSaved={() => {
            setModal(null);
            load();
          }}
        />
      )}
    </div>
  );
}

interface CategoryTreeRowProps {
  category: Category;
  depth: number;
  group: number | "root";
  dragState: DragState | null;
  setDragState: (state: DragState | null) => void;
  reorder: (group: number | "root", draggedId: number, targetId: number) => void;
  onEdit: (category: Category) => void;
  onArchive: (id: number) => void;
}

function CategoryTreeRow({ category, depth, group, dragState, setDragState, reorder, onEdit, onArchive }: CategoryTreeRowProps) {
  return (
    <div>
      <div
        className="cat-row"
        draggable
        style={depth > 0 ? { marginLeft: 22 * depth } : undefined}
        onDragStart={() => setDragState({ id: category.id, group })}
        onDragOver={(e) => dragState?.group === group && e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          if (dragState?.group === group) reorder(group, dragState.id, category.id);
          setDragState(null);
        }}
      >
        <span>
          <span className="drag">⠿</span>
          <span className="dot" style={{ background: category.color }}></span>
          {depth === 0 ? <b>{category.name}</b> : category.name}
        </span>
        <div className="row-actions">
          <span className="icon-btn split" onClick={() => onEdit(category)}>
            ✎
          </span>
          <span className="icon-btn remove" onClick={() => onArchive(category.id)}>
            🗑
          </span>
        </div>
      </div>
      {category.children.map((child) => (
        <CategoryTreeRow
          key={child.id}
          category={child}
          depth={depth + 1}
          group={category.id}
          dragState={dragState}
          setDragState={setDragState}
          reorder={reorder}
          onEdit={onEdit}
          onArchive={onArchive}
        />
      ))}
    </div>
  );
}

function collectSubtreeIds(category: Category): number[] {
  return [category.id, ...category.children.flatMap(collectSubtreeIds)];
}

function CategoryModal({
  mode,
  category,
  tree,
  onClose,
  onSaved,
}: {
  mode: "new" | "edit";
  category?: Category;
  tree: Category[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(category?.name ?? "");
  const [parentId, setParentId] = useState<number | "">(category?.parent_id ?? "");
  const [color, setColor] = useState(category?.color ?? "#6f8f6a");
  const [isIncome, setIsIncome] = useState(category?.is_income ?? false);

  // A category can be parented under anything at any depth, except itself
  // or one of its own descendants (would create a cycle).
  const excludedIds = new Set(category ? collectSubtreeIds(category) : []);
  const parentOptions = flattenAllCategories(tree).filter((o) => !excludedIds.has(o.id));

  async function save() {
    if (mode === "new") {
      await categoriesApi.create({ name, parent_id: parentId === "" ? null : parentId, color, is_income: isIncome });
    } else if (category) {
      await categoriesApi.update(category.id, {
        name,
        color,
        parent_id: parentId === "" ? null : parentId,
        move_to_root: parentId === "",
        is_income: isIncome,
      });
    }
    onSaved();
  }

  return (
    <Modal
      title={mode === "new" ? "New category" : "Edit category"}
      onClose={onClose}
      onSubmit={save}
      submitLabel={mode === "new" ? "Create category" : "Save changes"}
    >
      <div className="field">
        <label>Name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. subscriptions" />
      </div>
      <div className="field">
        <label>Parent category</label>
        <select value={parentId} onChange={(e) => setParentId(e.target.value === "" ? "" : Number(e.target.value))}>
          <option value="">None (top level)</option>
          {parentOptions.map((o) => (
            <option key={o.id} value={o.id}>
              {o.path}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label>Colour</label>
        <input type="color" value={color} style={{ width: 60, padding: 2 }} onChange={(e) => setColor(e.target.value)} />
      </div>
      <div className="field">
        <label>
          <input
            type="checkbox"
            checked={isIncome}
            onChange={(e) => setIsIncome(e.target.checked)}
            style={{ marginRight: 6 }}
          />
          Income category
        </label>
        <p className="sub" style={{ marginTop: 4, marginBottom: 0 }}>
          Reporting only — flips this category's actual amounts to read as money received instead of spent.
          Applies to all of its subcategories too. Doesn't change any transaction data.
        </p>
      </div>
    </Modal>
  );
}

/** One-line human-readable summary of a rule condition. is_deposit/ is_withdrawal carry no value
 * (they match on the split's sign alone), so they're worded as a plain statement instead of the
 * usual field/operator/ value template -- which would otherwise print a bare empty "". */
function conditionSummary(
  c: { field: ConditionField; operator: ConditionOperator; value: string },
  accountName: (id: string) => string,
): string {
  if (c.operator === "is_deposit") return `${c.field} is a deposit/credit`;
  if (c.operator === "is_withdrawal") return `${c.field} is a withdrawal/debit`;
  if (c.field === "account") {
    const names = c.value
      .split(",")
      .filter((part) => part.trim() !== "")
      .map((id) => `"${accountName(id.trim())}"`);
    return `account ${c.operator === "not_in" ? "is not" : "is"} ${names.join(" or ")}`;
  }
  return `${c.field} ${c.operator} "${c.value}"`;
}

/** Combines the conditions of the given rules (in list order) for the "Merge rules" flow, deduping
 * exact field/operator/value repeats across rules, and defaulting the target category to the first
 * selected rule's. */
function buildMergeInitial(sourceRules: Rule[]) {
  const seen = new Set<string>();
  const conditions: { field: ConditionField; operator: ConditionOperator; value: string }[] = [];
  for (const rule of sourceRules) {
    for (const c of rule.conditions) {
      const key = `${c.field}|${c.operator}|${c.value}`;
      if (seen.has(key)) continue;
      seen.add(key);
      conditions.push({ field: c.field, operator: c.operator, value: c.value });
    }
  }
  return {
    matchType: "any" as MatchType,
    conditions,
    targetCategoryId: sourceRules[0].target_category_id,
  };
}

function RulesTab() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [modal, setModal] = useState<null | { mode: "new" | "edit"; rule?: Rule }>(null);
  const [showRunModal, setShowRunModal] = useState(false);
  const [appliedCount, setAppliedCount] = useState<number | null>(null);
  const [mergeMode, setMergeMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [mergeModalRules, setMergeModalRules] = useState<Rule[] | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);

  function load() {
    rulesApi.list().then(setRules);
  }

  function exitMergeMode() {
    setMergeMode(false);
    setSelectedIds(new Set());
  }

  function toggleSelected(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  useEffect(() => {
    load();
    categoriesApi.list().then(setCategories);
    accountsApi.list().then(setAccounts);
  }, []);

  // Categories can nest to any depth (docs/requirements.md §2.2), so this has to walk the whole
  // tree rather than just top-level + one child deep -- flattenAllCategories already does that
  // recursively.
  const categoryPaths = flattenAllCategories(categories);
  const categoryName = (id: number) => categoryPaths.find((o) => o.id === id)?.path ?? `#${id}`;
  const accountName = (id: string) => accounts.find((a) => String(a.id) === id)?.name ?? `#${id}`;

  async function move(index: number, direction: -1 | 1) {
    const ids = rules.map((r) => r.id);
    const target = index + direction;
    if (target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    await rulesApi.reorder(ids);
    load();
  }

  return (
    <div>
      <div className="toolbar">
        <span style={{ color: "var(--ink-2)", fontSize: 12.5 }}>
          {mergeMode ? `Select rules to merge — ${selectedIds.size} selected.` : "Order matters — first match wins."}
        </span>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {appliedCount !== null && (
            <span className="sub">
              Applied {appliedCount} suggestion{appliedCount === 1 ? "" : "s"} — review in Transactions.
            </span>
          )}
          {mergeMode ? (
            <>
              <button className="btn ghost sm" onClick={exitMergeMode}>
                Cancel
              </button>
              <button
                className="btn sm"
                disabled={selectedIds.size < 2}
                onClick={() => setMergeModalRules(rules.filter((r) => selectedIds.has(r.id)))}
              >
                Merge {selectedIds.size > 0 ? `(${selectedIds.size})` : ""}
              </button>
            </>
          ) : (
            <>
              <button className="btn ghost sm" onClick={() => setMergeMode(true)}>
                Merge rules
              </button>
              <button
                className="btn ghost sm"
                onClick={() => {
                  setAppliedCount(null);
                  setShowRunModal(true);
                }}
              >
                Run rules
              </button>
              <button className="btn sm" onClick={() => setModal({ mode: "new" })}>
                + New rule
              </button>
            </>
          )}
        </div>
      </div>
      {rules.map((rule, i) => (
        <div className="rule-row" key={rule.id}>
          <div>
            {mergeMode ? (
              <input
                type="checkbox"
                style={{ marginRight: 10 }}
                checked={selectedIds.has(rule.id)}
                onChange={() => toggleSelected(rule.id)}
              />
            ) : (
              <>
                <span className="drag" style={{ cursor: "pointer" }} onClick={() => move(i, -1)}>
                  ▲
                </span>
                <span className="drag" style={{ cursor: "pointer" }} onClick={() => move(i, 1)}>
                  ▼
                </span>
              </>
            )}
            <b>{i + 1}.</b> if {rule.match_type.toUpperCase()}:{" "}
            {rule.conditions.map((c) => conditionSummary(c, accountName)).join(" · ")} →{" "}
            <span className="tag" style={{ background: "#ece5f2", color: "#8a6aa0" }}>
              {categoryName(rule.target_category_id)}
            </span>
          </div>
          {!mergeMode && (
            <div className="row-actions">
              <span className="icon-btn split" onClick={() => setModal({ mode: "edit", rule })}>
                ✎
              </span>
              <span
                className="icon-btn remove"
                onClick={async () => {
                  await rulesApi.remove(rule.id);
                  load();
                }}
              >
                🗑
              </span>
            </div>
          )}
        </div>
      ))}

      {modal && (
        <RuleModal
          mode={modal.mode}
          rule={modal.rule}
          categories={categories}
          onClose={() => setModal(null)}
          onSaved={() => {
            setModal(null);
            load();
          }}
        />
      )}

      {mergeModalRules && (
        <RuleModal
          mode="new"
          categories={categories}
          mergeSourceRules={mergeModalRules}
          initial={buildMergeInitial(mergeModalRules)}
          onClose={() => setMergeModalRules(null)}
          onSaved={() => {
            setMergeModalRules(null);
            exitMergeMode();
            load();
          }}
        />
      )}

      {showRunModal && (
        <RunRulesModal
          categories={categories}
          onClose={() => setShowRunModal(false)}
          onApplied={(count) => {
            setShowRunModal(false);
            setAppliedCount(count);
          }}
        />
      )}
    </div>
  );
}

function BackupTab() {
  return (
    <BackupCards
      download={backupApi.download}
      restore={backupApi.restore}
      fallbackFilename="budgeter-backup.db"
      accept=".db,.sqlite"
      downloadTitle="Download backup"
      downloadText="Exports your books as a single file — copy it somewhere safe. Other users' data isn't included."
      downloadLabel="Download backup (.db)"
      restoreTitle="Restore from backup"
      restoreText="Replaces all of your current data with the contents of the selected file."
      restoreInputLabel="Backup file"
      confirmText="This will overwrite all of your current data with the selected backup. Continue?"
      doneText="Restore complete. Reload the app to see the restored data."
    />
  );
}

function HistoryRetentionTab() {
  const [retentionDays, setRetentionDays] = useState<number | null>(null);
  const [input, setInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    settingsApi.getRetention().then((r) => {
      setRetentionDays(r.retention_days);
      setInput(String(r.retention_days));
    });
  }, []);

  async function save() {
    const days = Number(input);
    setSaving(true);
    setSaved(false);
    try {
      const { retention_days } = await settingsApi.updateRetention(days);
      setRetentionDays(retention_days);
      setInput(String(retention_days));
      setSaved(true);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card" style={{ maxWidth: 420 }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>Change history retention</div>
      <p className="sub" style={{ marginBottom: 12 }}>
        How long to keep account/category/transaction change history before it's purged and can no longer be
        undone. Lowering this purges older entries immediately.
      </p>
      <div className="field">
        <label>Retention (days)</label>
        <input
          type="number"
          min={1}
          max={3650}
          style={{ width: 120 }}
          value={input}
          onChange={(e) => {
            setInput(e.target.value);
            setSaved(false);
          }}
        />
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button className="btn sm" onClick={save} disabled={saving || retentionDays === null}>
          {saving ? "Saving…" : "Save"}
        </button>
        {saved && <span className="sub">Saved.</span>}
      </div>
    </div>
  );
}

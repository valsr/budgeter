import { useEffect, useState } from "react";
import { backupApi } from "../api/backup";
import { categoriesApi } from "../api/categories";
import { rulesApi } from "../api/rules";
import type { Category, ConditionField, ConditionOperator, MatchType, Rule } from "../api/types";
import { Modal } from "../components/Modal";

type Tab = "api" | "cats" | "rules" | "backup";

export function Settings() {
  const [tab, setTab] = useState<Tab>("api");

  return (
    <div>
      <h1>Settings</h1>
      <p className="sub">API access, category taxonomy, and categorization rules.</p>
      <div className="settings-tabs">
        <span className={tab === "api" ? "active" : ""} onClick={() => setTab("api")}>
          API key
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
      </div>

      {tab === "api" && <ApiKeyTab />}
      {tab === "cats" && <CategoriesTab />}
      {tab === "rules" && <RulesTab />}
      {tab === "backup" && <BackupTab />}
    </div>
  );
}

function ApiKeyTab() {
  const apiKey = import.meta.env.VITE_API_KEY ?? "dev-local-api-key";
  const [revealed, setRevealed] = useState(false);
  return (
    <div>
      <div className="field" style={{ maxWidth: 420 }}>
        <label>API key — used by the MCP adapter / skill</label>
        <input value={revealed ? apiKey : "•".repeat(Math.max(8, apiKey.length))} readOnly />
      </div>
      <button className="btn ghost sm" onClick={() => setRevealed((r) => !r)}>
        {revealed ? "Hide" : "Show"}
      </button>
    </div>
  );
}

function CategoriesTab() {
  const [tree, setTree] = useState<Category[]>([]);
  const [modal, setModal] = useState<null | { mode: "new" | "edit"; category?: Category; parentId?: number | null }>(
    null,
  );
  const [dragState, setDragState] = useState<{ id: number; group: number | "root" } | null>(null);

  function load() {
    categoriesApi.list().then(setTree);
  }

  useEffect(load, []);

  async function reorder(group: number | "root", draggedId: number, targetId: number) {
    const siblings = group === "root" ? tree : tree.find((p) => p.id === group)?.children ?? [];
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

  return (
    <div>
      <div className="toolbar">
        <span className="sub" style={{ margin: 0 }}>
          Drag <span className="drag">⠿</span> to reorder within a group.
        </span>
        <button className="btn sm" onClick={() => setModal({ mode: "new", parentId: null })}>
          + New category
        </button>
      </div>
      <div>
        {tree.map((parent) => (
          <div key={parent.id}>
            <div
              className="cat-row"
              draggable
              onDragStart={() => setDragState({ id: parent.id, group: "root" })}
              onDragOver={(e) => dragState?.group === "root" && e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (dragState?.group === "root") reorder("root", dragState.id, parent.id);
                setDragState(null);
              }}
            >
              <span>
                <span className="drag">⠿</span>
                <span className="dot" style={{ background: parent.color }}></span>
                <b>{parent.name}</b>
              </span>
              <div className="row-actions">
                <span className="icon-btn split" onClick={() => setModal({ mode: "edit", category: parent })}>
                  ✎
                </span>
                <span
                  className="icon-btn remove"
                  onClick={async () => {
                    await categoriesApi.archive(parent.id);
                    load();
                  }}
                >
                  ⌀
                </span>
              </div>
            </div>
            {parent.children.map((child) => (
              <div
                key={child.id}
                className="cat-row"
                draggable
                style={{ marginLeft: 22 }}
                onDragStart={() => setDragState({ id: child.id, group: parent.id })}
                onDragOver={(e) => dragState?.group === parent.id && e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  if (dragState?.group === parent.id) reorder(parent.id, dragState.id, child.id);
                  setDragState(null);
                }}
              >
                <span>
                  <span className="drag">⠿</span>
                  <span className="dot" style={{ background: child.color }}></span>
                  {child.name}
                </span>
                <div className="row-actions">
                  <span className="icon-btn split" onClick={() => setModal({ mode: "edit", category: child })}>
                    ✎
                  </span>
                  <span
                    className="icon-btn remove"
                    onClick={async () => {
                      await categoriesApi.archive(child.id);
                      load();
                    }}
                  >
                    ⌀
                  </span>
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>

      {modal && (
        <CategoryModal
          mode={modal.mode}
          category={modal.category}
          parentOptions={tree}
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

function CategoryModal({
  mode,
  category,
  parentOptions,
  onClose,
  onSaved,
}: {
  mode: "new" | "edit";
  category?: Category;
  parentOptions: Category[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(category?.name ?? "");
  const [parentId, setParentId] = useState<number | "">(category?.parent_id ?? "");
  const [color, setColor] = useState(category?.color ?? "#6f8f6a");

  async function save() {
    if (mode === "new") {
      await categoriesApi.create({ name, parent_id: parentId === "" ? null : parentId, color });
    } else if (category) {
      await categoriesApi.update(category.id, {
        name,
        color,
        parent_id: parentId === "" ? null : parentId,
        move_to_root: parentId === "",
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
          {parentOptions
            .filter((p) => p.id !== category?.id)
            .map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
        </select>
      </div>
      <div className="field">
        <label>Colour</label>
        <input type="color" value={color} style={{ width: 60, padding: 2 }} onChange={(e) => setColor(e.target.value)} />
      </div>
    </Modal>
  );
}

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

function RulesTab() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [modal, setModal] = useState<null | { mode: "new" | "edit"; rule?: Rule }>(null);

  function load() {
    rulesApi.list().then(setRules);
  }

  useEffect(() => {
    load();
    categoriesApi.list().then(setCategories);
  }, []);

  const categoryName = (id: number) => {
    for (const p of categories) {
      if (p.id === id) return p.name;
      for (const c of p.children) if (c.id === id) return `${p.name}:${c.name}`;
    }
    return `#${id}`;
  };

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
        <span style={{ color: "var(--ink-2)", fontSize: 12.5 }}>Order matters — first match wins.</span>
        <button className="btn sm" onClick={() => setModal({ mode: "new" })}>
          + New rule
        </button>
      </div>
      {rules.map((rule, i) => (
        <div className="rule-row" key={rule.id}>
          <div>
            <span className="drag" style={{ cursor: "pointer" }} onClick={() => move(i, -1)}>
              ▲
            </span>
            <span className="drag" style={{ cursor: "pointer" }} onClick={() => move(i, 1)}>
              ▼
            </span>
            <b>{i + 1}.</b> if {rule.match_type.toUpperCase()}:{" "}
            {rule.conditions.map((c) => `${c.field} ${c.operator} "${c.value}"`).join(" · ")} →{" "}
            <span className="tag" style={{ background: "#ece5f2", color: "#8a6aa0" }}>
              {categoryName(rule.target_category_id)}
            </span>
          </div>
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
              ⌀
            </span>
          </div>
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
    </div>
  );
}

function RuleModal({
  mode,
  rule,
  categories,
  onClose,
  onSaved,
}: {
  mode: "new" | "edit";
  rule?: Rule;
  categories: Category[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [matchType, setMatchType] = useState<MatchType>(rule?.match_type ?? "all");
  const [conditions, setConditions] = useState(
    rule?.conditions.map((c) => ({ field: c.field, operator: c.operator, value: c.value })) ?? [
      { field: "name" as ConditionField, operator: "contains" as ConditionOperator, value: "" },
    ],
  );
  const leafOptions: { id: number; path: string }[] = [];
  for (const p of categories) for (const c of p.children) leafOptions.push({ id: c.id, path: `${p.name}:${c.name}` });
  for (const p of categories) if (p.children.length === 0) leafOptions.push({ id: p.id, path: p.name });
  const [targetCategoryId, setTargetCategoryId] = useState<number | "">(
    rule?.target_category_id ?? leafOptions[0]?.id ?? "",
  );

  function updateCondition(i: number, patch: Partial<(typeof conditions)[number]>) {
    setConditions((prev) => prev.map((c, idx) => (idx === i ? { ...c, ...patch } : c)));
  }

  async function save() {
    if (targetCategoryId === "") return;
    const payload = { match_type: matchType, conditions, target_category_id: targetCategoryId };
    if (mode === "new") {
      await rulesApi.create(payload);
    } else if (rule) {
      await rulesApi.update(rule.id, payload);
    }
    onSaved();
  }

  return (
    <Modal
      title={mode === "new" ? "New rule" : "Edit rule"}
      onClose={onClose}
      onSubmit={save}
      submitLabel="Save rule"
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
              ⌀
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
    </Modal>
  );
}

function BackupTab() {
  const [restoring, setRestoring] = useState(false);

  async function download() {
    const { blob, filename } = await backupApi.download();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename ?? "budgeter-backup.db";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function restore(file: File) {
    if (!confirm("This will overwrite all current data with the selected backup. Continue?")) return;
    setRestoring(true);
    try {
      await backupApi.restore(file);
      alert("Restore complete. Reload the app to see the restored data.");
    } finally {
      setRestoring(false);
    }
  }

  return (
    <div>
      <div className="card" style={{ maxWidth: 520 }}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>Download backup</div>
        <p className="sub" style={{ marginBottom: 12 }}>
          Exports the full database as a single file — copy it somewhere safe.
        </p>
        <button className="btn" onClick={download}>
          Download backup (.db)
        </button>
      </div>
      <div className="card" style={{ maxWidth: 520, borderColor: "#e3cfa3", background: "#fdfbf7" }}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>Restore from backup</div>
        <p className="sub" style={{ marginBottom: 12 }}>
          Replaces all current data with the contents of the selected file.{" "}
          <b style={{ color: "var(--c5)" }}>This can't be undone.</b>
        </p>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            type="file"
            accept=".db,.sqlite"
            style={{ fontSize: 12.5 }}
            disabled={restoring}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) restore(file);
            }}
          />
        </div>
      </div>
    </div>
  );
}

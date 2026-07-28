import { useEffect, useState } from "react";
import { backupApi } from "../api/backup";
import { categoriesApi } from "../api/categories";
import { setApiKey } from "../api/client";
import { rulesApi } from "../api/rules";
import { settingsApi } from "../api/settings";
import type { Category, Rule } from "../api/types";
import { Modal } from "../components/Modal";
import { RuleModal } from "../components/RuleModal";

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
  const [apiKey, setKey] = useState<string | null>(null);
  const [revealed, setRevealed] = useState(false);
  const [regenerating, setRegenerating] = useState(false);

  useEffect(() => {
    settingsApi.getApiKey().then((r) => setKey(r.api_key));
  }, []);

  async function regenerate() {
    if (
      !confirm(
        "Regenerate the API key? The current key stops working immediately — any MCP adapter or " +
          "skill using it will need the new value.",
      )
    ) {
      return;
    }
    setRegenerating(true);
    try {
      const { api_key } = await settingsApi.regenerateApiKey();
      setApiKey(api_key); // keep this browser session authenticated with the new key
      setKey(api_key);
      setRevealed(true); // surface it immediately since it can't be re-fetched in plaintext-friendly UX otherwise
    } finally {
      setRegenerating(false);
    }
  }

  const display = apiKey ?? "";
  return (
    <div>
      <div className="field" style={{ maxWidth: 420 }}>
        <label>API key — used by the MCP adapter / skill</label>
        <input value={revealed ? display : "•".repeat(Math.max(8, display.length))} readOnly />
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn ghost sm" onClick={() => setRevealed((r) => !r)} disabled={apiKey === null}>
          {revealed ? "Hide" : "Show"}
        </button>
        <button className="btn sm" onClick={regenerate} disabled={regenerating || apiKey === null}>
          {regenerating ? "Regenerating…" : "Regenerate"}
        </button>
      </div>
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
                  🗑
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
                    🗑
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
              🗑
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

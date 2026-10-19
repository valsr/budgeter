import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { sharedBudgetsApi } from "../../api/sharedBudgets";
import type { SharedCategoryPatch } from "../../api/sharedBudgets";
import type { DirectoryUser, SharedBudget, SharedCategory, SharedMember } from "../../api/types";
import { useAuth } from "../../auth/context";
import { MONTH_LABELS } from "../../components/reportColumns";
import { CURRENT_YEAR, sharedTreeOrder, subtreeIds, YEARS } from "./tree";

/** Run a request whose failure the global error toast already reports; the screen just stays as it was. */
async function attempt<T>(request: Promise<T>): Promise<T | undefined> {
  try {
    return await request;
  } catch {
    return undefined;
  }
}

type Amounts = Record<number, Record<number, string>>;

/** One cell's text as a number, null when blank. */
function cellValue(raw: string | undefined): number | null {
  const text = (raw ?? "").trim();
  return text === "" ? null : Number(text);
}

export function SetupTab({ budget, onChange }: { budget: SharedBudget; onChange: (b: SharedBudget) => void }) {
  const id = budget.id;
  const { user } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState(budget.name);
  const [members, setMembers] = useState<SharedMember[]>(budget.members);
  const [directory, setDirectory] = useState<DirectoryUser[]>([]);
  const [toAdd, setToAdd] = useState("");
  const [categories, setCategories] = useState<SharedCategory[]>([]);
  const [newCat, setNewCat] = useState({ name: "", parent: "", income: false });
  const [year, setYear] = useState(CURRENT_YEAR);
  const [amounts, setAmounts] = useState<Amounts>({});
  // What the server holds for `year`, as last loaded or saved; null until it has loaded (or when
  // loading failed), and then the grid is read-only -- saving it would wipe the year.
  const [saved, setSaved] = useState<{ year: number; values: Amounts } | null>(null);
  const loaded = saved !== null && saved.year === year;
  const [amountsNote, setAmountsNote] = useState("");

  const tree = sharedTreeOrder(categories);
  const active = tree.filter((n) => !n.category.archived);
  const addable = directory.filter((d) => !members.some((m) => m.user_id === d.id));

  useEffect(() => {
    attempt(sharedBudgetsApi.directory()).then((d) => d && setDirectory(d));
    loadCategories();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    setAmounts({});
    setSaved(null);
    setAmountsNote("");
    let stale = false;
    attempt(sharedBudgetsApi.amounts(id, year)).then((rows) => {
      if (stale) return;
      if (!rows) {
        setAmountsNote(`Couldn't load the amounts for ${year}.`);
        return;
      }
      const next: Amounts = {};
      for (const a of rows) (next[a.shared_category_id] ??= {})[a.month] = String(a.amount);
      setAmounts(next);
      setSaved({ year, values: next });
    });
    return () => {
      stale = true;
    };
  }, [id, year]);

  function loadCategories() {
    attempt(sharedBudgetsApi.categories(id)).then((c) => c && setCategories(c));
  }

  async function saveName() {
    const updated = await attempt(sharedBudgetsApi.rename(id, name.trim()));
    if (updated) onChange(updated);
  }

  async function saveMembers() {
    const updated = await attempt(sharedBudgetsApi.setMembers(id, members.map((m) => m.user_id)));
    if (!updated) return;
    if (!updated.members.some((m) => m.user_id === user.id)) navigate("/shared-budgets");
    else onChange(updated);
  }

  function addMember() {
    const person = directory.find((d) => String(d.id) === toAdd);
    if (person) setMembers([...members, { user_id: person.id, username: person.username, is_disabled: false }]);
    setToAdd("");
  }

  async function updateCategory(categoryId: number, patch: SharedCategoryPatch) {
    await attempt(sharedBudgetsApi.updateCategory(id, categoryId, patch));
    loadCategories();
  }

  async function addCategory() {
    const parent_id = newCat.parent ? Number(newCat.parent) : null;
    const created = await attempt(
      sharedBudgetsApi.createCategory(id, { name: newCat.name.trim(), parent_id, is_income: newCat.income }),
    );
    if (created) setNewCat({ name: "", parent: "", income: false });
    loadCategories();
  }

  async function deleteCategory(c: SharedCategory) {
    if (!confirm(`Delete "${c.name}" and its amounts for every year?`)) return;
    await attempt(sharedBudgetsApi.deleteCategory(id, c.id));
    loadCategories();
  }

  async function saveAmounts() {
    if (!saved || saved.year !== year) return;
    const base = saved.values;
    // Only the cells that differ from what was loaded: the server deletes a cell sent as null.
    const lines = active.flatMap(({ category }) =>
      MONTH_LABELS.map((_, i) => ({
        shared_category_id: category.id,
        month: i + 1,
        amount: cellValue(amounts[category.id]?.[i + 1]),
        before: cellValue(base[category.id]?.[i + 1]),
      })).filter((l) => l.amount !== l.before),
    );
    if (lines.some((l) => l.amount !== null && !Number.isFinite(l.amount))) {
      setAmountsNote("Amounts must be numbers.");
      return;
    }
    if (lines.length === 0) {
      setAmountsNote("Nothing to save.");
      return;
    }
    const sent = amounts;
    const savedYear = year;
    const body = lines.map(({ shared_category_id, month, amount }) => ({ shared_category_id, month, amount }));
    if (!(await attempt(sharedBudgetsApi.setAmounts(id, savedYear, body)))) return;
    setSaved((current) => {
      if (!current || current.year !== savedYear) return current;
      const values: Amounts = {};
      for (const [cat, months] of Object.entries(current.values)) values[Number(cat)] = { ...months };
      for (const l of lines) (values[l.shared_category_id] ??= {})[l.month] = sent[l.shared_category_id]?.[l.month] ?? "";
      return { year: savedYear, values };
    });
    setAmountsNote("Saved.");
  }

  async function deleteBudget() {
    if (!confirm(`Delete "${budget.name}" for every member? This can't be undone.`)) return;
    try {
      await sharedBudgetsApi.remove(id);
      navigate("/shared-budgets");
    } catch {
      // Reported by the global error toast.
    }
  }

  return (
    <div>
      <div className="card">
        <div className="field" style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
          <div>
            <label htmlFor="shared-budget-rename">Name</label>
            <input id="shared-budget-rename" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <button type="button" className="btn" disabled={!name.trim() || name.trim() === budget.name} onClick={saveName}>
            Save name
          </button>
        </div>
      </div>

      <div className="card">
        <div className="section-title">Members</div>
        {members.map((m) => (
          <div key={m.user_id} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
            <span>
              {m.username}
              {m.user_id === user.id && " (you)"}
              {m.is_disabled && <span className="sub"> (disabled)</span>}
            </span>
            <button
              type="button"
              className="btn ghost sm"
              aria-label={`Remove ${m.username}`}
              disabled={members.length === 1}
              onClick={() => setMembers(members.filter((x) => x.user_id !== m.user_id))}
            >
              Remove
            </button>
          </div>
        ))}
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
          <select aria-label="Add member" value={toAdd} onChange={(e) => setToAdd(e.target.value)}>
            <option value="">Add a member…</option>
            {addable.map((d) => (
              <option key={d.id} value={d.id}>
                {d.username}
              </option>
            ))}
          </select>
          <button type="button" className="btn ghost" disabled={!toAdd} onClick={addMember}>
            Add
          </button>
          <button type="button" className="btn" onClick={saveMembers}>
            Save members
          </button>
        </div>
      </div>

      <div className="card">
        <div className="section-title">Shared categories</div>
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Parent</th>
              <th>Income</th>
              <th>Archived</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {tree.map(({ category: c, depth }) => {
              const blocked = subtreeIds(categories, c.id);
              return (
                <tr key={c.id}>
                  <td style={{ paddingLeft: 14 + 22 * depth }}>
                    <input
                      aria-label={`Name of ${c.name}`}
                      defaultValue={c.name}
                      key={c.name}
                      onBlur={(e) => {
                        const v = e.target.value.trim();
                        if (v && v !== c.name) updateCategory(c.id, { name: v });
                        else e.target.value = c.name;
                      }}
                    />
                  </td>
                  <td>
                    <select
                      aria-label={`Parent of ${c.name}`}
                      value={c.parent_id ?? ""}
                      onChange={(e) => updateCategory(c.id, { parent_id: e.target.value ? Number(e.target.value) : null })}
                    >
                      <option value="">(top level)</option>
                      {tree
                        .filter((n) => !blocked.has(n.category.id))
                        .map((n) => (
                          <option key={n.category.id} value={n.category.id}>
                            {n.path}
                          </option>
                        ))}
                    </select>
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`${c.name} is income`}
                      checked={c.is_income}
                      onChange={(e) => updateCategory(c.id, { is_income: e.target.checked })}
                    />
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`${c.name} is archived`}
                      checked={c.archived}
                      onChange={(e) => updateCategory(c.id, { archived: e.target.checked })}
                    />
                  </td>
                  <td>
                    <button type="button" className="btn ghost sm" onClick={() => deleteCategory(c)}>
                      Delete
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
          <input
            aria-label="New category name"
            placeholder="New category"
            value={newCat.name}
            onChange={(e) => setNewCat({ ...newCat, name: e.target.value })}
          />
          <select
            aria-label="New category parent"
            value={newCat.parent}
            onChange={(e) => setNewCat({ ...newCat, parent: e.target.value })}
          >
            <option value="">(top level)</option>
            {tree.map((n) => (
              <option key={n.category.id} value={n.category.id}>
                {n.path}
              </option>
            ))}
          </select>
          <label>
            <input
              type="checkbox"
              checked={newCat.income}
              onChange={(e) => setNewCat({ ...newCat, income: e.target.checked })}
            />{" "}
            Income
          </label>
          <button type="button" className="btn ghost" disabled={!newCat.name.trim()} onClick={addCategory}>
            Add category
          </button>
        </div>
      </div>

      <div className="card">
        <div className="section-title" style={{ display: "flex", gap: 8, alignItems: "center" }}>
          Monthly amounts for
          <select aria-label="Amounts year" value={year} onChange={(e) => setYear(Number(e.target.value))}>
            {YEARS.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table id="budget-edit-table" style={{ minWidth: 1100 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left" }}>Category</th>
                {MONTH_LABELS.map((label, i) => (
                  <th key={label} className={"right" + (i % 2 === 1 ? " month-alt" : "")}>
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {active.map(({ category: c, depth }) => (
                <tr key={c.id}>
                  <td style={{ paddingLeft: 14 + 14 * depth, color: "var(--ink-2)" }}>{c.name}</td>
                  {MONTH_LABELS.map((label, i) => (
                    <td key={label} className={i % 2 === 1 ? "month-alt" : undefined}>
                      <input
                        className="month-input"
                        aria-label={`${c.name} ${label}`}
                        value={amounts[c.id]?.[i + 1] ?? ""}
                        disabled={!loaded}
                        onChange={(e) => {
                          setAmountsNote("");
                          setAmounts({ ...amounts, [c.id]: { ...amounts[c.id], [i + 1]: e.target.value } });
                        }}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
          <button type="button" className="btn" disabled={!loaded || active.length === 0} onClick={saveAmounts}>
            Save amounts
          </button>
          {amountsNote && <span className="sub">{amountsNote}</span>}
        </div>
      </div>

      <div className="card danger">
        <button type="button" className="btn ghost" onClick={deleteBudget}>
          Delete shared budget
        </button>
      </div>
    </div>
  );
}

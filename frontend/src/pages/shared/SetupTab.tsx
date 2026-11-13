import { Fragment, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { sharedBudgetsApi } from "../../api/sharedBudgets";
import type { SharedCategoryPatch } from "../../api/sharedBudgets";
import type { DirectoryUser, SharedBudget, SharedCategory, SharedMember } from "../../api/types";
import { useAuth } from "../../auth/context";
import { MONTH_LABELS } from "../../components/reportColumns";
import { formatMoney } from "../../format";
import { LoadError } from "./LoadError";
import { CURRENT_YEAR, sharedTreeOrder, YEARS } from "./tree";

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
  const categoriesLoaded = useRef(false);
  const [categoriesFailed, setCategoriesFailed] = useState(false);
  const [newCat, setNewCat] = useState({ name: "", income: false });
  // The category whose [+] was clicked: a name input for its new sub-category shows under it.
  const [addingUnder, setAddingUnder] = useState<{ parent: SharedCategory; name: string } | null>(null);
  const [year, setYear] = useState(CURRENT_YEAR);
  const [amounts, setAmounts] = useState<Amounts>({});
  // What the server holds for `year`, as last loaded or saved; null until it has loaded (or when
  // loading failed), and then the grid is read-only -- saving it would wipe the year.
  const [saved, setSaved] = useState<{ year: number; values: Amounts } | null>(null);
  const loaded = saved !== null && saved.year === year;
  const [amountsNote, setAmountsNote] = useState("");

  const tree = sharedTreeOrder(categories);
  const active = tree.filter((n) => !n.category.archived);
  // A supercategory's months are the sums of its sub-categories', not typed in.
  const activeKids = new Map<number, number[]>();
  for (const { category: c } of active) {
    if (c.parent_id !== null) activeKids.set(c.parent_id, [...(activeKids.get(c.parent_id) ?? []), c.id]);
  }
  const editable = active.filter((n) => !activeKids.has(n.category.id));
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
    attempt(sharedBudgetsApi.categories(id)).then((c) => {
      // A failed reload after an edit keeps the tree already on screen; only a tree that never
      // loaded is replaced by the error, rather than passing for an empty one.
      if (c) {
        setCategories(c);
        categoriesLoaded.current = true;
      }
      setCategoriesFailed(!categoriesLoaded.current);
    });
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
    const created = await attempt(
      sharedBudgetsApi.createCategory(id, { name: newCat.name.trim(), parent_id: null, is_income: newCat.income }),
    );
    if (created) setNewCat({ name: "", income: false });
    loadCategories();
  }

  async function addSubcategory() {
    if (!addingUnder || !addingUnder.name.trim()) return;
    const { parent, name } = addingUnder;
    // A sub-category starts out on the same side (income or spending) as its parent.
    const created = await attempt(
      sharedBudgetsApi.createCategory(id, { name: name.trim(), parent_id: parent.id, is_income: parent.is_income }),
    );
    if (created) setAddingUnder(null);
    loadCategories();
  }

  /** What a cell shows: typed text for a leaf, the sum of its sub-categories for a supercategory. */
  function monthTotal(categoryId: number, month: number): number {
    const kids = activeKids.get(categoryId);
    if (!kids) return cellValue(amounts[categoryId]?.[month]) || 0;
    // Like the report: a supercategory's own stored amount (from before it had sub-categories) counts too.
    return kids.reduce((sum, k) => sum + monthTotal(k, month), cellValue(amounts[categoryId]?.[month]) || 0);
  }

  function yearTotal(categoryId: number): number {
    return MONTH_LABELS.reduce((sum, _, i) => sum + monthTotal(categoryId, i + 1), 0);
  }

  function setCell(categoryId: number, month: number, value: string) {
    setAmountsNote("");
    setAmounts((current) => ({ ...current, [categoryId]: { ...current[categoryId], [month]: value } }));
  }

  /** Copy one month's amount into every later month of the year. */
  function copyToRemaining(categoryId: number, month: number) {
    setAmountsNote("");
    setAmounts((current) => {
      const row = { ...current[categoryId] };
      for (let m = month + 1; m <= 12; m++) row[m] = row[month] ?? "";
      return { ...current, [categoryId]: row };
    });
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
    const lines = editable.flatMap(({ category }) =>
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

      <div className="card full-bleed">
        <div className="section-title" style={{ display: "flex", gap: 8, alignItems: "center" }}>
          Shared categories and monthly amounts for
          <select aria-label="Amounts year" value={year} onChange={(e) => setYear(Number(e.target.value))}>
            {YEARS.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </div>
        {categoriesFailed ? (
          <LoadError message="Couldn't load the shared categories." onRetry={loadCategories} />
        ) : (
          <>
            <div className="shared-grid-scroll">
              <table id="shared-grid">
                <thead>
                  <tr>
                    <th className="frozen frozen-name">Category</th>
                    <th className="frozen frozen-actions">Actions</th>
                    <th className="frozen frozen-tally right">Year</th>
                    {MONTH_LABELS.map((label, i) => (
                      <th key={label} className={"right" + (i % 2 === 1 ? " month-alt" : "")}>
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {tree.map(({ category: c, depth }) => {
                    const isSuper = activeKids.has(c.id);
                    const isEditable = !c.archived && !isSuper;
                    return (
                      <Fragment key={c.id}>
                        <tr className={c.archived ? "archived" : undefined}>
                          <td className="frozen frozen-name" style={{ paddingLeft: 10 + 18 * depth }}>
                            <div className="name-cell">
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
                              <button
                                type="button"
                                className="icon-btn"
                                aria-label={`Delete ${c.name}`}
                                title="Delete category"
                                onClick={() => deleteCategory(c)}
                              >
                                ×
                              </button>
                            </div>
                          </td>
                          <td className="frozen frozen-actions">
                            <div className="row-actions">
                              <button
                                type="button"
                                className="icon-btn"
                                aria-label={`Add a sub-category under ${c.name}`}
                                title="Add a sub-category"
                                onClick={() => setAddingUnder({ parent: c, name: "" })}
                              >
                                +
                              </button>
                              <label title="Income category">
                                <input
                                  type="checkbox"
                                  aria-label={`${c.name} is income`}
                                  checked={c.is_income}
                                  onChange={(e) => updateCategory(c.id, { is_income: e.target.checked })}
                                />
                                Inc
                              </label>
                              <label title="Archived: takes no new amounts">
                                <input
                                  type="checkbox"
                                  aria-label={`${c.name} is archived`}
                                  checked={c.archived}
                                  onChange={(e) => updateCategory(c.id, { archived: e.target.checked })}
                                />
                                Arch
                              </label>
                            </div>
                          </td>
                          <td className="frozen frozen-tally right" aria-label={`${c.name} year total`}>
                            {c.archived ? "—" : formatMoney(yearTotal(c.id))}
                          </td>
                          {MONTH_LABELS.map((label, i) => {
                            const month = i + 1;
                            const alt = i % 2 === 1 ? " month-alt" : "";
                            if (!isEditable) {
                              return (
                                <td key={label} className={"right computed" + alt} aria-label={`${c.name} ${label}`}>
                                  {isSuper ? formatMoney(monthTotal(c.id, month)) : ""}
                                </td>
                              );
                            }
                            return (
                              <td key={label} className={"amount-cell" + alt}>
                                <input
                                  className="month-input"
                                  aria-label={`${c.name} ${label}`}
                                  value={amounts[c.id]?.[month] ?? ""}
                                  disabled={!loaded}
                                  onChange={(e) => setCell(c.id, month, e.target.value)}
                                />
                                {month < 12 && loaded && (
                                  <button
                                    type="button"
                                    className="copy-right"
                                    aria-label={`Copy ${c.name} ${label} to the remaining months`}
                                    title="Copy to the remaining months"
                                    onClick={() => copyToRemaining(c.id, month)}
                                  >
                                    →
                                  </button>
                                )}
                              </td>
                            );
                          })}
                        </tr>
                        {addingUnder?.parent.id === c.id && (
                          <tr>
                            <td className="frozen frozen-name" style={{ paddingLeft: 10 + 18 * (depth + 1) }}>
                              <input
                                autoFocus
                                aria-label={`New sub-category under ${c.name}`}
                                placeholder="New sub-category"
                                value={addingUnder.name}
                                onChange={(e) => setAddingUnder({ parent: c, name: e.target.value })}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") addSubcategory();
                                  if (e.key === "Escape") setAddingUnder(null);
                                }}
                              />
                            </td>
                            <td className="frozen frozen-actions">
                              <div className="row-actions">
                                <button
                                  type="button"
                                  className="btn sm"
                                  disabled={!addingUnder.name.trim()}
                                  onClick={addSubcategory}
                                >
                                  Add
                                </button>
                                <button type="button" className="btn ghost sm" onClick={() => setAddingUnder(null)}>
                                  Cancel
                                </button>
                              </div>
                            </td>
                            <td className="frozen frozen-tally" />
                            <td colSpan={12} />
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12, flexWrap: "wrap" }}>
              <button type="button" className="btn" disabled={!loaded || editable.length === 0} onClick={saveAmounts}>
                Save amounts
              </button>
              {amountsNote && <span className="sub" style={{ margin: 0 }}>{amountsNote}</span>}
              <span style={{ flex: 1 }} />
              <input
                aria-label="New category name"
                placeholder="New top-level category"
                value={newCat.name}
                onChange={(e) => setNewCat({ ...newCat, name: e.target.value })}
              />
              <label>
                <input
                  type="checkbox"
                  aria-label="New category is income"
                  checked={newCat.income}
                  onChange={(e) => setNewCat({ ...newCat, income: e.target.checked })}
                />{" "}
                Income
              </label>
              <button type="button" className="btn ghost" disabled={!newCat.name.trim()} onClick={addCategory}>
                Add category
              </button>
            </div>
          </>
        )}
      </div>

      <div className="card danger">
        <button type="button" className="btn ghost" onClick={deleteBudget}>
          Delete shared budget
        </button>
      </div>
    </div>
  );
}

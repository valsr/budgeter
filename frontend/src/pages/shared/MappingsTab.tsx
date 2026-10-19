import { useEffect, useMemo, useState } from "react";
import { activeCategories, categoriesApi, flattenAllCategories } from "../../api/categories";
import { sharedBudgetsApi } from "../../api/sharedBudgets";
import type { Category, SharedCategory, SharedLink } from "../../api/types";
import { CategoryCombobox } from "../../components/CategoryCombobox";
import { sharedTreeOrder } from "./tree";

/** The caller's own categories mapped onto this budget's shared ones. A category can feed only one
 * shared category, so one already used in any row is left out of every row's picker. */
export function MappingsTab({ budgetId }: { budgetId: number }) {
  const [shared, setShared] = useState<SharedCategory[] | null>(null);
  // Fetched with archived ones too: an archived category can still be mapped, and needs a name.
  const [own, setOwn] = useState<Category[]>([]);
  const [links, setLinks] = useState<SharedLink[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  // Bumped after each pick so that row's picker remounts empty, ready for another.
  const [pickCount, setPickCount] = useState(0);

  useEffect(() => {
    Promise.all([sharedBudgetsApi.categories(budgetId), categoriesApi.list(true), sharedBudgetsApi.links(budgetId)])
      .then(([s, o, l]) => {
        setShared(s);
        setOwn(o);
        setLinks(l);
      })
      .catch(() => setShared([]));
  }, [budgetId]);

  const pathOf = useMemo(() => new Map(flattenAllCategories(own).map((o) => [o.id, o.path])), [own]);
  const pickable = useMemo(() => activeCategories(own), [own]);
  const mapped = useMemo(() => new Set(links.map((l) => l.category_id)), [links]);

  function edit(next: SharedLink[]) {
    setLinks(next);
    setSaved(false);
  }

  async function save() {
    setSaving(true);
    try {
      await sharedBudgetsApi.setLinks(budgetId, links);
      setSaved(true);
    } catch {
      // The global error toast has already said why; the edits stay on screen to retry.
    } finally {
      setSaving(false);
    }
  }

  if (shared === null) return <p className="sub">Loading…</p>;
  const rows = sharedTreeOrder(shared).filter((n) => !n.category.archived);
  if (rows.length === 0) return <p className="sub">This budget has no shared categories yet — add some under Setup.</p>;

  return (
    <div>
      <p className="sub">
        Pick which of your own categories count towards each shared category. Mapping a parent counts everything
        beneath it. Only you see your mappings; the others see your totals.
      </p>
      <table>
        <thead>
          <tr>
            <th>Shared category</th>
            <th>Your categories</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ category, depth }) => {
            const mine = links.filter((l) => l.shared_category_id === category.id);
            return (
              <tr key={category.id}>
                <td style={{ paddingLeft: 14 + 22 * depth, verticalAlign: "top" }}>{category.name}</td>
                <td>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 6 }}>
                    {mine.map((l) => {
                      const name = pathOf.get(l.category_id) ?? `#${l.category_id}`;
                      return (
                        <span
                          key={l.category_id}
                          style={{ border: "1px solid var(--line)", borderRadius: 12, padding: "1px 4px 1px 10px" }}
                        >
                          <span>{name}</span>{" "}
                          <button
                            type="button"
                            className="btn ghost sm"
                            aria-label={`Unmap ${name}`}
                            onClick={() => edit(links.filter((x) => x.category_id !== l.category_id))}
                          >
                            ×
                          </button>
                        </span>
                      );
                    })}
                  </div>
                  <CategoryCombobox
                    key={pickCount}
                    categories={pickable}
                    value={null}
                    mode="filter"
                    optionSource="all"
                    placeholder="Add one of your categories…"
                    excludeIds={mapped}
                    onChange={(categoryId) => {
                      if (categoryId === null || mapped.has(categoryId)) return;
                      edit([...links, { category_id: categoryId, shared_category_id: category.id }]);
                      setPickCount((n) => n + 1);
                    }}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12 }}>
        <button type="button" className="btn" onClick={save} disabled={saving}>
          Save mappings
        </button>
        {saved && <span className="sub">Saved.</span>}
      </div>
    </div>
  );
}

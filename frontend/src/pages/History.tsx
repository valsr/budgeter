import { Fragment, useEffect, useState } from "react";
import { historyApi } from "../api/history";
import type { ChangeEntityType, ChangeGroup, UndoResult } from "../api/types";

const PAGE_SIZE = 50;

interface Filters {
  entityType: ChangeEntityType | "";
  dateFrom: string;
  dateTo: string;
}

const EMPTY_FILTERS: Filters = { entityType: "", dateFrom: "", dateTo: "" };

export function History() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<{ items: ChangeGroup[]; total: number } | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);

  function load() {
    historyApi
      .list({
        entityType: filters.entityType || undefined,
        dateFrom: filters.dateFrom || undefined,
        dateTo: filters.dateTo || undefined,
        page,
        pageSize: PAGE_SIZE,
      })
      .then(setData);
  }

  useEffect(load, [filters, page]);

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  function toggleSelected(groupId: string) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  }

  function toggleExpanded(groupId: string) {
    setExpanded((s) => {
      const next = new Set(s);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  }

  function reportOutcomes(results: UndoResult[]) {
    const failed = results.filter((r) => r.status === "skipped");
    if (failed.length > 0) {
      alert(
        failed.length === results.length
          ? `Couldn't undo: ${failed.map((f) => f.reason).join("; ")}`
          : `${results.length - failed.length} undone, ${failed.length} skipped: ${failed
              .map((f) => f.reason)
              .join("; ")}`,
      );
    }
  }

  async function undoOne(group: ChangeGroup) {
    if (group.is_stale && !confirm("This entity has changed again since this edit — undo anyway?")) return;
    setBusy(true);
    try {
      const { results } = await historyApi.undo([group.group_id]);
      reportOutcomes(results);
      setSelected((s) => {
        const next = new Set(s);
        next.delete(group.group_id);
        return next;
      });
      load();
    } finally {
      setBusy(false);
    }
  }

  async function undoSelected() {
    const staleSelected = items.filter((g) => selected.has(g.group_id) && g.is_stale);
    if (
      staleSelected.length > 0 &&
      !confirm(`${staleSelected.length} of the selected changes were superseded by later edits — undo anyway?`)
    ) {
      return;
    }
    setBusy(true);
    try {
      const { results } = await historyApi.undo([...selected]);
      reportOutcomes(results);
      setSelected(new Set());
      load();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1>History</h1>
      <p className="sub">Every change to accounts, categories, and transactions. Select one or more to undo.</p>

      <div className="filters-row">
        <select
          value={filters.entityType}
          onChange={(e) => {
            setPage(1);
            setFilters((f) => ({ ...f, entityType: e.target.value as ChangeEntityType | "" }));
          }}
        >
          <option value="">All types</option>
          <option value="account">Accounts</option>
          <option value="category">Categories</option>
          <option value="transaction">Transactions</option>
        </select>
        <input
          type="date"
          title="From date"
          value={filters.dateFrom}
          onChange={(e) => {
            setPage(1);
            setFilters((f) => ({ ...f, dateFrom: e.target.value }));
          }}
        />
        <input
          type="date"
          title="To date"
          value={filters.dateTo}
          onChange={(e) => {
            setPage(1);
            setFilters((f) => ({ ...f, dateTo: e.target.value }));
          }}
        />
      </div>

      <div className="toolbar">
        <span className="sub" style={{ margin: 0 }}>
          {selected.size > 0 ? `${selected.size} selected` : ""}
        </span>
        <button className="btn sm" disabled={selected.size === 0 || busy} onClick={undoSelected}>
          Undo selected {selected.size > 0 ? `(${selected.size})` : ""}
        </button>
      </div>

      <table>
        <thead>
          <tr>
            <th></th>
            <th>When</th>
            <th>Type</th>
            <th>Change</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((group) => {
            const isExpanded = expanded.has(group.group_id);
            const isUndone = group.undone_at !== null;
            return (
              <Fragment key={group.group_id}>
                <tr className={isUndone ? "undone-row" : ""}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selected.has(group.group_id)}
                      disabled={isUndone}
                      onChange={() => toggleSelected(group.group_id)}
                    />
                  </td>
                  <td>{new Date(group.created_at).toLocaleString()}</td>
                  <td>
                    <span className="tag">{group.entity_type}</span>
                  </td>
                  <td>
                    <span onClick={() => toggleExpanded(group.group_id)} style={{ cursor: "pointer" }}>
                      {isExpanded ? "▾ " : "▸ "}
                      {group.summary}
                    </span>
                    {isUndone && (
                      <span className="tag" style={{ marginLeft: 8 }}>
                        undone
                      </span>
                    )}
                    {!isUndone && group.is_stale && (
                      <span className="tag" style={{ marginLeft: 8, background: "#fbe8c8", color: "#a06a1a" }}>
                        superseded since
                      </span>
                    )}
                  </td>
                  <td className="ctrl-cell">
                    {!isUndone && (
                      <button className="btn ghost sm" disabled={busy} onClick={() => undoOne(group)}>
                        Undo
                      </button>
                    )}
                  </td>
                </tr>
                {isExpanded && (
                  <tr>
                    <td></td>
                    <td colSpan={4}>
                      <pre style={{ fontSize: 12, whiteSpace: "pre-wrap", margin: "4px 0" }}>
                        {JSON.stringify(group.items, null, 2)}
                      </pre>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
          {items.length === 0 && (
            <tr>
              <td colSpan={5} className="sub">
                No changes recorded yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <div className="pagination">
        <span>
          Showing {total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total}
        </span>
        <div className="pages">
          <span onClick={() => setPage((p) => Math.max(1, p - 1))}>‹</span>
          <span className="cur">{page}</span>
          {totalPages > 1 && <span>of {totalPages}</span>}
          <span onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>›</span>
        </div>
      </div>
    </div>
  );
}

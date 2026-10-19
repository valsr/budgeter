import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { sharedBudgetsApi } from "../api/sharedBudgets";
import type { SharedBudget as SharedBudgetData } from "../api/types";
import { MappingsTab } from "./shared/MappingsTab";
import { ReportTab } from "./shared/ReportTab";
import { SetupTab } from "./shared/SetupTab";

const TABS = ["Report", "Setup", "My mappings"] as const;
type Tab = (typeof TABS)[number];

/** One shared budget: its report, its setup, and the caller's own mappings into it. */
export function SharedBudget() {
  const id = Number(useParams().id);
  const [budget, setBudget] = useState<SharedBudgetData | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("Report");

  useEffect(() => {
    setBudget(null);
    setFailure(null);
    sharedBudgetsApi.get(id).then(setBudget, (e: unknown) =>
      setFailure(e instanceof ApiError && e.status === 404 ? "Shared budget not found." : "Couldn't load this shared budget."),
    );
  }, [id]);

  if (failure) {
    return (
      <div>
        <h1>Shared budget</h1>
        <p className="sub">{failure}</p>
        <Link to="/shared-budgets">Back to shared budgets</Link>
      </div>
    );
  }
  if (!budget) return <p className="sub">Loading…</p>;
  return (
    <div>
      <div className="toolbar">
        <h1>{budget.name}</h1>
      </div>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            className={"btn" + (t === tab ? "" : " ghost")}
            aria-pressed={t === tab}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>
      <div data-testid="tab-panel">
        {tab === "Report" && <ReportTab budgetId={budget.id} />}
        {tab === "Setup" && <SetupTab budget={budget} onChange={setBudget} />}
        {tab === "My mappings" && <MappingsTab budgetId={budget.id} />}
      </div>
    </div>
  );
}

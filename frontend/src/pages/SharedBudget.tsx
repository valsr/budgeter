import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { sharedBudgetsApi } from "../api/sharedBudgets";
import type { SharedBudget as SharedBudgetData } from "../api/types";

const TABS = ["Report", "Setup", "My mappings"] as const;
type Tab = (typeof TABS)[number];

/** One shared budget. The tab panels are filled in by later tasks. */
export function SharedBudget() {
  const id = Number(useParams().id);
  const [budget, setBudget] = useState<SharedBudgetData | null>(null);
  const [tab, setTab] = useState<Tab>("Report");

  useEffect(() => {
    sharedBudgetsApi.get(id).then(setBudget);
  }, [id]);

  if (!budget) return <div />;
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
        <p className="sub">{tab} view is coming soon.</p>
      </div>
    </div>
  );
}

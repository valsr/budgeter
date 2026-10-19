import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { sharedBudgetsApi } from "../api/sharedBudgets";
import type { DirectoryUser, SharedBudget } from "../api/types";
import { useAuth } from "../auth/context";
import { Modal } from "../components/Modal";

export function SharedBudgets() {
  const [budgets, setBudgets] = useState<SharedBudget[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    sharedBudgetsApi
      .list()
      .then(setBudgets, () => {}) // the global error toast reports a failure
      .finally(() => setLoaded(true));
  }, []);

  return (
    <div>
      <div className="toolbar">
        <div>
          <h1>Shared budgets</h1>
          <p className="sub" style={{ marginBottom: 0 }}>
            Budgets you plan together with other people on this server.
          </p>
        </div>
        <button className="btn" onClick={() => setCreating(true)}>
          New shared budget
        </button>
      </div>

      {loaded && budgets.length === 0 ? (
        <p className="sub">No shared budgets yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Members</th>
            </tr>
          </thead>
          <tbody>
            {budgets.map((b) => (
              <tr key={b.id}>
                <td>
                  <Link to={`/shared-budgets/${b.id}`}>{b.name}</Link>
                </td>
                <td>{b.members.map((m) => m.username).join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {creating && (
        <NewSharedBudgetModal
          onClose={() => setCreating(false)}
          onCreated={(budget) => {
            setBudgets((prev) => [...prev, budget]);
            setCreating(false);
          }}
        />
      )}
    </div>
  );
}

function NewSharedBudgetModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (budget: SharedBudget) => void;
}) {
  const { user } = useAuth();
  const [name, setName] = useState("");
  const [people, setPeople] = useState<DirectoryUser[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  useEffect(() => {
    sharedBudgetsApi.directory().then((all) => setPeople(all.filter((p) => p.id !== user.id)));
  }, [user.id]);

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function submit() {
    try {
      const created = await sharedBudgetsApi.create({
        name: name.trim(),
        member_ids: people.filter((p) => selected.has(p.id)).map((p) => p.id),
      });
      onCreated(created);
    } catch {
      // Reported by the global error toast; the dialog stays open to retry.
    }
  }

  return (
    <Modal
      title="New shared budget"
      onClose={onClose}
      onSubmit={submit}
      submitLabel="Create"
      submitDisabled={name.trim() === ""}
    >
      <div className="field">
        <label htmlFor="shared-budget-name">Name</label>
        <input
          id="shared-budget-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Household"
        />
      </div>
      <div className="field">
        <label>Members (you are always included)</label>
        {people.length === 0 && <p className="sub">No other users on this server.</p>}
        {people.map((p) => (
          <div key={p.id}>
            <label>
              <input type="checkbox" checked={selected.has(p.id)} onChange={() => toggle(p.id)} />{" "}
              {p.username}
            </label>
          </div>
        ))}
      </div>
    </Modal>
  );
}

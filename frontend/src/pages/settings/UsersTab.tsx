import type { FormEvent } from "react";
import { useEffect, useState } from "react";
import { adminApi } from "../../api/admin";
import type { AdminUser } from "../../api/types";
import { useAuth } from "../../auth/context";
import { formatTimestamp } from "../../format";

type UserPatch = Parameters<typeof adminApi.updateUser>[1];

export function UsersTab() {
  const { user: me, refresh } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [adding, setAdding] = useState(false);

  function load() {
    adminApi.listUsers().then(setUsers);
  }

  useEffect(load, []);

  // Refusals (the last-admin guard, a taken username) arrive as the global
  // error toast; either way the list is re-read so it shows what's true.
  async function apply(target: AdminUser, change: () => Promise<unknown>) {
    try {
      await change();
      // Changing your own account can alter what you're allowed to see here.
      if (target.id === me.id) await refresh();
    } catch {
      // already toasted
    }
    load();
  }

  const patch = (target: AdminUser, body: UserPatch) => apply(target, () => adminApi.updateUser(target.id, body));

  function resetPassword(target: AdminUser) {
    const next = prompt(`New password for ${target.username} (at least 8 characters):`);
    if (!next) return;
    patch(target, { password: next });
  }

  function remove(target: AdminUser) {
    if (
      !confirm(
        `Delete the user "${target.username}" and all of their data — accounts, transactions, budgets, ` +
          "rules and history? This can't be undone.",
      )
    ) {
      return;
    }
    apply(target, () => adminApi.deleteUser(target.id));
  }

  async function add(e: FormEvent) {
    e.preventDefault();
    setAdding(true);
    try {
      await adminApi.createUser(username, password);
      setUsername("");
      setPassword("");
    } catch {
      // already toasted
    } finally {
      setAdding(false);
    }
    load();
  }

  return (
    <div>
      <p className="sub" style={{ marginBottom: 14 }}>
        Everyone with a login on this server. Each user has their own separate books; admins manage accounts
        but can't see anyone else's data.
      </p>

      <form className="filters-row" style={{ marginBottom: 16, alignItems: "flex-end" }} onSubmit={add}>
        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor="new-username">New username</label>
          <input
            id="new-username"
            autoCapitalize="none"
            autoComplete="off"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </div>
        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor="new-password">Initial password</label>
          <input
            id="new-password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <button className="btn sm" type="submit" disabled={adding || username === "" || password === ""}>
          Add user
        </button>
      </form>

      <table>
        <thead>
          <tr>
            <th>Username</th>
            <th>Role</th>
            <th>Status</th>
            <th>Created</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td>
                {u.username}
                {u.id === me.id && <span className="badge asset">you</span>}
              </td>
              <td>{u.is_admin ? "admin" : "user"}</td>
              <td>
                <span className={"status " + (u.is_disabled ? "warn" : "ok")}>
                  {u.is_disabled ? "disabled" : "active"}
                </span>
              </td>
              <td>{formatTimestamp(u.created_at)}</td>
              <td className="right">
                <span style={{ display: "inline-flex", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
                  <button className="btn ghost sm" onClick={() => patch(u, { is_disabled: !u.is_disabled })}>
                    {u.is_disabled ? "Enable" : "Disable"}
                  </button>
                  <button className="btn ghost sm" onClick={() => patch(u, { is_admin: !u.is_admin })}>
                    {u.is_admin ? "Remove admin" : "Make admin"}
                  </button>
                  <button className="btn ghost sm" onClick={() => resetPassword(u)}>
                    Reset password
                  </button>
                  <button className="btn ghost sm" onClick={() => remove(u)}>
                    Delete
                  </button>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

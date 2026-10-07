import type { FormEvent } from "react";
import { useEffect, useState } from "react";
import { authApi } from "../../api/auth";
import { settingsApi } from "../../api/settings";
import { useAuth } from "../../auth/context";

const errorText = (e: unknown) => (e instanceof Error ? e.message : "Something went wrong");

export function AccountTab() {
  const { user } = useAuth();
  return (
    <div>
      <p className="sub" style={{ marginBottom: 14 }}>
        Signed in as <b>{user.username}</b>
        {user.is_admin ? " (admin)" : ""}.
      </p>
      <PasswordCard />
      <ApiKeyCard />
      <DeleteAccountCard />
    </div>
  );
}

function PasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [saving, setSaving] = useState(false);

  const mismatch = confirm !== "" && next !== confirm;
  const ready = current !== "" && next !== "" && next === confirm;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!ready) return;
    setSaving(true);
    setMessage(null);
    try {
      await authApi.changePassword(current, next);
      setCurrent("");
      setNext("");
      setConfirm("");
      setMessage({ ok: true, text: "Password changed." });
    } catch (err) {
      setMessage({ ok: false, text: errorText(err) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="card" style={{ maxWidth: 520 }} onSubmit={submit}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>Change password</div>
      <p className="sub" style={{ marginBottom: 12 }}>
        Logs you out everywhere else. At least 8 characters.
      </p>
      <div className="field">
        <label htmlFor="pw-current">Current password</label>
        <input
          id="pw-current"
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="pw-new">New password</label>
        <input
          id="pw-new"
          type="password"
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="pw-confirm">Confirm new password</label>
        <input
          id="pw-confirm"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
      </div>
      {mismatch && (
        <p className="sub" style={{ color: "var(--c5)", marginBottom: 10 }}>
          Passwords don't match
        </p>
      )}
      {message && (
        <p className="sub" style={{ color: message.ok ? undefined : "var(--c5)", marginBottom: 10 }}>
          {message.text}
        </p>
      )}
      <button className="btn sm" type="submit" disabled={!ready || saving}>
        Change password
      </button>
    </form>
  );
}

function ApiKeyCard() {
  const [hasKey, setHasKey] = useState<boolean | null>(null);
  // Only ever set straight after a regenerate: the server keeps a hash, so
  // this is the one moment the key can be shown.
  const [revealed, setRevealed] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState(false);

  useEffect(() => {
    settingsApi.getApiKey().then((r) => setHasKey(r.has_key));
  }, []);

  async function regenerate() {
    if (
      hasKey &&
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
      setRevealed(api_key);
      setHasKey(true);
    } finally {
      setRegenerating(false);
    }
  }

  return (
    <div className="card" style={{ maxWidth: 520 }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>API key</div>
      <p className="sub" style={{ marginBottom: 12 }}>
        Lets the MCP adapter or a script act on your books, as you.{" "}
        {hasKey === null ? "" : <b>{hasKey ? "A key is set" : "No key yet"}</b>}
      </p>
      {revealed !== null && (
        <div className="field">
          <input value={revealed} readOnly aria-label="New API key" onFocus={(e) => e.target.select()} />
          <p className="sub" style={{ marginTop: 6, color: "var(--c5)" }}>
            Copy it now — it won't be shown again.
          </p>
        </div>
      )}
      <button className="btn sm" onClick={regenerate} disabled={regenerating || hasKey === null}>
        {regenerating ? "Generating…" : hasKey ? "Regenerate" : "Generate key"}
      </button>
    </div>
  );
}

function DeleteAccountCard() {
  const { user, refresh } = useAuth();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  async function remove() {
    if (
      !confirm(
        `Delete the account "${user.username}" and all of its data — accounts, transactions, budgets, ` +
          "rules and history? This can't be undone.",
      )
    ) {
      return;
    }
    setDeleting(true);
    setError(null);
    try {
      await authApi.deleteMe(password);
      // The session died with the account; this drops back to the login screen.
      await refresh();
    } catch (err) {
      setError(errorText(err));
      setDeleting(false);
    }
  }

  return (
    <div className="card" style={{ maxWidth: 520, borderColor: "#e3cfa3", background: "#fdfbf7" }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>Delete my account</div>
      <p className="sub" style={{ marginBottom: 12 }}>
        Removes your login and all of your books. <b style={{ color: "var(--c5)" }}>This can't be undone</b> —
        download a backup first if you might want the data.
      </p>
      <div className="field">
        <label htmlFor="delete-password">Password</label>
        <input
          id="delete-password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </div>
      {error && (
        <p className="sub" style={{ color: "var(--c5)", marginBottom: 10 }}>
          {error}
        </p>
      )}
      <button className="btn ghost sm" onClick={remove} disabled={password === "" || deleting}>
        Delete my account
      </button>
    </div>
  );
}

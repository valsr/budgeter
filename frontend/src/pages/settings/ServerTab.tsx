import type { FormEvent } from "react";
import { useEffect, useState } from "react";
import { adminApi } from "../../api/admin";
import type { ServerHealth, ServerSettings } from "../../api/admin";
import { useAuth } from "../../auth/context";
import { saveBlob } from "../../download";
import { formatBytes, formatDuration, formatTimestamp } from "../../format";

export function ServerTab() {
  const { refresh } = useAuth();
  const [settings, setSettings] = useState<ServerSettings | null>(null);
  const [registrationOpen, setRegistrationOpen] = useState<boolean | null>(null);
  const [restoring, setRestoring] = useState(false);

  useEffect(() => {
    adminApi.getSettings().then((s) => {
      setSettings(s);
      setRegistrationOpen(s.registration_open);
    });
  }, []);

  async function toggleRegistration(open: boolean) {
    const saved = await adminApi.updateSettings({ registration_open: open });
    setRegistrationOpen(saved.registration_open);
  }

  async function download() {
    const { blob, filename } = await adminApi.downloadBackup();
    saveBlob(blob, filename ?? "budgeter-server-backup.zip");
  }

  async function restore(file: File) {
    if (
      !confirm(
        "This replaces every user's data and accounts with the archive. You may need to log in again. Continue?",
      )
    ) {
      return;
    }
    setRestoring(true);
    try {
      await adminApi.restoreBackup(file);
      alert("Restore complete.");
      // Sessions came from the archive too: find out whether this one survived.
      await refresh();
    } finally {
      setRestoring(false);
    }
  }

  return (
    <div>
      <HealthCard />
      {settings && <NetworkCard settings={settings} onSaved={setSettings} />}
      <div className="card" style={{ maxWidth: 520 }}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>Registration</div>
        <p className="sub" style={{ marginBottom: 12 }}>
          When off, only an admin can add users (Settings → Users). Every new account is an admin until
          another admin changes that.
        </p>
        <label style={{ display: "inline-flex", gap: 8, alignItems: "center", fontSize: 13 }}>
          <input
            type="checkbox"
            checked={registrationOpen ?? false}
            disabled={registrationOpen === null}
            onChange={(e) => toggleRegistration(e.target.checked)}
          />
          Allow new registrations
        </label>
      </div>
      <div className="card" style={{ maxWidth: 520 }}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>Download server backup</div>
        <p className="sub" style={{ marginBottom: 12 }}>
          One archive with every user's login and books. It contains everyone's data — keep it somewhere safe.
        </p>
        <button className="btn" onClick={download}>
          Download server backup (.zip)
        </button>
      </div>
      <div className="card" style={{ maxWidth: 520, borderColor: "#e3cfa3", background: "#fdfbf7" }}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>Restore server from backup</div>
        <p className="sub" style={{ marginBottom: 12 }}>
          Replaces all users and all of their data with the archive's. Users created since it was taken are
          removed. <b style={{ color: "var(--c5)" }}>This can't be undone.</b>
        </p>
        <input
          type="file"
          accept=".zip"
          aria-label="Server backup archive"
          style={{ fontSize: 12.5 }}
          disabled={restoring}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) restore(file);
          }}
        />
      </div>
    </div>
  );
}

const warn = { color: "var(--c5)" };

function NetworkCard({
  settings,
  onSaved,
}: {
  settings: ServerSettings;
  onSaved: (settings: ServerSettings) => void;
}) {
  const [port, setPort] = useState(String(settings.port));
  const [sslEnabled, setSslEnabled] = useState(settings.ssl_enabled);
  const [certfile, setCertfile] = useState(settings.ssl_certfile ?? "");
  const [keyfile, setKeyfile] = useState(settings.ssl_keyfile ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const portNumber = Number(port);
  const portValid = /^\d+$/.test(port.trim()) && portNumber >= 1 && portNumber <= 65535;

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!portValid) return;
    setSaving(true);
    setError(null);
    try {
      // The server checks the certificate and key before saving anything,
      // so a refusal here leaves the previous, working settings in place.
      onSaved(
        await adminApi.updateSettings(
          { port: portNumber, ssl_enabled: sslEnabled, ssl_certfile: certfile, ssl_keyfile: keyfile },
          { silent: true },
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save the settings");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="card" style={{ maxWidth: 520 }} onSubmit={save}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>Port and HTTPS</div>
      <p className="sub" style={{ marginBottom: 12 }}>
        Read when the server starts — changes take effect after a restart. With HTTPS on, the server
        won't start if the certificate or key can't be found, rather than fall back to plain HTTP.
      </p>
      {!settings.managed && (
        <div className="notice" style={{ marginBottom: 12 }}>
          The running server isn't applying these settings: it was started with a plain{" "}
          <code>uvicorn</code> command, which sets its own port and TLS. Start it with{" "}
          <code>python -m app.serve</code> to use them.
        </div>
      )}
      {settings.restart_required && (
        <div className="notice" style={{ marginBottom: 12 }}>
          Restart the server to apply the saved port and HTTPS settings.
        </div>
      )}
      {(settings.port_override !== null || settings.ssl_disabled_override) && (
        <div className="notice" style={{ marginBottom: 12 }}>
          Overridden by the server's environment:{" "}
          {settings.port_override !== null && <code>BUDGETER_PORT={settings.port_override}</code>}
          {settings.port_override !== null && settings.ssl_disabled_override && ", "}
          {settings.ssl_disabled_override && <code>BUDGETER_SSL_DISABLED</code>}. The values below are
          saved but not used while it is set.
        </div>
      )}
      <div className="field" style={{ maxWidth: 140 }}>
        <label htmlFor="server-port">Port</label>
        <input id="server-port" inputMode="numeric" value={port} onChange={(e) => setPort(e.target.value)} />
      </div>
      {!portValid && (
        <p className="sub" style={{ ...warn, marginBottom: 10 }}>
          Port must be between 1 and 65535
        </p>
      )}
      <label style={{ display: "inline-flex", gap: 8, alignItems: "center", fontSize: 13, marginBottom: 12 }}>
        <input type="checkbox" checked={sslEnabled} onChange={(e) => setSslEnabled(e.target.checked)} />
        Serve over HTTPS (SSL)
      </label>
      <div className="field">
        <label htmlFor="ssl-certfile">Certificate file</label>
        <input
          id="ssl-certfile"
          placeholder="/path/on/the/server/fullchain.pem"
          spellCheck={false}
          disabled={!sslEnabled}
          value={certfile}
          onChange={(e) => setCertfile(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="ssl-keyfile">Private key file</label>
        <input
          id="ssl-keyfile"
          placeholder="/path/on/the/server/privkey.pem"
          spellCheck={false}
          disabled={!sslEnabled}
          value={keyfile}
          onChange={(e) => setKeyfile(e.target.value)}
        />
      </div>
      <p className="sub" style={{ marginBottom: 12 }}>
        Absolute paths to PEM files on the server (inside the container, if it runs in one). The key must
        not be passphrase-protected.
      </p>
      {error && (
        <p className="sub" style={{ ...warn, marginBottom: 10 }}>
          {error}
        </p>
      )}
      <button className="btn sm" type="submit" disabled={!portValid || saving}>
        Save network settings
      </button>
    </form>
  );
}

const CHECK_LABELS: Record<string, string> = {
  server_db: "Server database",
  books: "Books files",
  ssl: "SSL certificate",
};

function HealthCard() {
  const [health, setHealth] = useState<ServerHealth | null>(null);

  function load() {
    adminApi.getHealth().then(setHealth);
  }

  useEffect(load, []);

  const rows: [string, string][] = health
    ? [
        [
          "Serving",
          health.serving
            ? `${health.serving.https ? "HTTPS" : "HTTP"} on port ${health.serving.port}`
            : "Started outside the launcher",
        ],
        ["Up for", `${formatDuration(health.uptime_seconds)} (since ${formatTimestamp(health.started_at)})`],
        [
          "Users",
          `${health.users.total} users (${health.users.active_admins} active admins, ${health.users.disabled} disabled)`,
        ],
        ...(health.storage
          ? ([
              [
                "Storage",
                `${health.storage.books_files} books files, ${formatBytes(health.storage.books_bytes)}; ` +
                  `server database ${formatBytes(health.storage.server_db_bytes)}`,
              ],
            ] as [string, string][])
          : []),
        ...(health.data_dir ? ([["Data directory", health.data_dir]] as [string, string][]) : []),
        ...(health.schema
          ? ([["Schema", `server ${health.schema.server ?? "?"}, books ${health.schema.books ?? "?"}`]] as [
              string,
              string,
            ][])
          : []),
        ["Python", health.python_version],
      ]
    : [];

  return (
    <div className="card" style={{ maxWidth: 520 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <div style={{ fontWeight: 600 }}>Server health</div>
        <button type="button" className="btn ghost sm" onClick={load}>
          Refresh
        </button>
      </div>
      {health && (
        <>
          <p style={{ marginBottom: 10 }}>
            <span className={"status " + (health.status === "ok" ? "ok" : "warn")}>
              {health.status === "ok" ? "Healthy" : "Needs attention"}
            </span>
          </p>
          <table className="health-table">
            <tbody>
              {Object.entries(health.checks).map(([name, value]) => (
                <tr key={name}>
                  <td>{CHECK_LABELS[name] ?? name}</td>
                  <td style={value === "ok" || value === "disabled" ? undefined : warn}>{value}</td>
                </tr>
              ))}
              {rows.map(([label, value]) => (
                <tr key={label}>
                  <td>{label}</td>
                  <td>{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

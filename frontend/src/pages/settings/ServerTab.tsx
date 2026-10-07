import { useEffect, useState } from "react";
import { adminApi } from "../../api/admin";
import { useAuth } from "../../auth/context";
import { saveBlob } from "../../download";

export function ServerTab() {
  const { refresh } = useAuth();
  const [registrationOpen, setRegistrationOpen] = useState<boolean | null>(null);
  const [restoring, setRestoring] = useState(false);

  useEffect(() => {
    adminApi.getSettings().then((s) => setRegistrationOpen(s.registration_open));
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

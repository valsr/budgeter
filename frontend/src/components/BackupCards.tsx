import type { ReactNode } from "react";
import { useState } from "react";
import { saveBlob } from "../download";

interface BackupCardsProps {
  download: () => Promise<{ blob: Blob; filename: string | null }>;
  restore: (file: File) => Promise<void>;
  fallbackFilename: string;
  /** File-picker filter, e.g. ".db,.sqlite". */
  accept: string;
  downloadTitle: string;
  downloadText: ReactNode;
  downloadLabel: string;
  restoreTitle: string;
  restoreText: ReactNode;
  restoreInputLabel: string;
  confirmText: string;
  doneText: string;
  onRestored?: () => void;
}

/** A download card and a restore card, for the personal and whole-server backups alike. */
export function BackupCards(props: BackupCardsProps) {
  const [restoring, setRestoring] = useState(false);

  async function download() {
    const { blob, filename } = await props.download();
    saveBlob(blob, filename ?? props.fallbackFilename);
  }

  async function restore(file: File) {
    if (!confirm(props.confirmText)) return;
    setRestoring(true);
    try {
      await props.restore(file);
      alert(props.doneText);
      props.onRestored?.();
    } finally {
      setRestoring(false);
    }
  }

  return (
    <>
      <div className="card" style={{ maxWidth: 520 }}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>{props.downloadTitle}</div>
        <p className="sub" style={{ marginBottom: 12 }}>
          {props.downloadText}
        </p>
        <button className="btn" onClick={download}>
          {props.downloadLabel}
        </button>
      </div>
      <div className="card danger" style={{ maxWidth: 520 }}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>{props.restoreTitle}</div>
        <p className="sub" style={{ marginBottom: 12 }}>
          {props.restoreText} <b style={{ color: "var(--c5)" }}>This can't be undone.</b>
        </p>
        <input
          type="file"
          accept={props.accept}
          aria-label={props.restoreInputLabel}
          style={{ fontSize: 12.5 }}
          disabled={restoring}
          onChange={(e) => {
            const file = e.target.files?.[0];
            // Cleared so picking the same file again after a cancel still fires.
            e.target.value = "";
            if (file) restore(file);
          }}
        />
      </div>
    </>
  );
}

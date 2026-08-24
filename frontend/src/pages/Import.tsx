import type { DragEvent } from "react";
import { useEffect, useRef, useState } from "react";
import { accountsApi } from "../api/accounts";
import { importsApi } from "../api/imports";
import type {
  Account,
  DetectAccountsOverride,
  DetectAccountsResponse,
  ImportBatch,
  ImportResolutionInput,
  ReviewQueueItem,
} from "../api/types";
import { ImportReviewModal } from "../components/ImportReviewModal";

export function Import() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [reviewItems, setReviewItems] = useState<ReviewQueueItem[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [detection, setDetection] = useState<DetectAccountsResponse | null>(null);
  const [showReviewModal, setShowReviewModal] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<ImportBatch[] | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function load() {
    importsApi.list().then(setBatches);
    importsApi.reviewItems().then(setReviewItems);
  }

  function loadAccounts() {
    return accountsApi.list().then(setAccounts);
  }

  useEffect(() => {
    loadAccounts();
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function resetFile() {
    setFile(null);
    setDetection(null);
    setShowReviewModal(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function handleFileSelected(selected: File) {
    setFile(selected);
    setDetection(null);
    setError(null);
    setLastResult(null);
    setDetecting(true);
    try {
      const result = await importsApi.detectAccounts(selected);
      if (result.accounts.length === 0) {
        setError("No transactions were found in this file.");
        resetFile();
        return;
      }
      setDetection(result);
      setShowReviewModal(true);
    } catch {
      setError("That file could not be read. Only .qif, .qfx, and .ofx exports are supported.");
      resetFile();
    } finally {
      setDetecting(false);
    }
  }

  /** Re-run the dry run when the user retargets a detected account, so the
   * imported/duplicate/needs-attention counts match the new destination. */
  async function refreshPreview(overrides: DetectAccountsOverride[]) {
    if (!file) return;
    setPreviewing(true);
    try {
      setDetection(await importsApi.detectAccounts(file, overrides));
    } catch {
      // Keep the stale counts on screen rather than losing the modal; the
      // commit itself is what actually matters.
    } finally {
      setPreviewing(false);
    }
  }

  async function commit(resolutions: ImportResolutionInput[]) {
    if (!file) return;
    setCommitting(true);
    setError(null);
    try {
      const result = await importsApi.commit(file, resolutions);
      setLastResult(result);
      resetFile();
      load();
      loadAccounts(); // any accounts created via "new_account" resolutions
    } catch {
      setError("The import failed. Nothing was changed.");
    } finally {
      setCommitting(false);
    }
  }

  async function resolve(itemId: number, action: "new" | "merge" | "skip") {
    await importsApi.resolveReviewItem(itemId, action);
    load();
  }

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragActive(true);
  }

  function handleDragLeave(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragActive(false);
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragActive(false);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) handleFileSelected(dropped);
  }

  const accountName = (id: number) => accounts.find((a) => a.id === id)?.name ?? `#${id}`;

  const resultTotals = (lastResult ?? []).reduce(
    (acc, b) => ({
      imported: acc.imported + b.imported_count,
      skipped: acc.skipped + b.skipped_duplicate_count,
      review: acc.review + b.needs_review_count,
    }),
    { imported: 0, skipped: 0, review: 0 },
  );

  return (
    <div>
      <h1>Import</h1>
      <p className="sub">
        Import a QIF, QFX, or OFX statement export. Pick a file first — the accounts it references
        are matched against your own, and you confirm where everything goes (and what will be
        imported, skipped, or flagged) before anything is written.
      </p>

      <div
        className={"dropzone" + (dragActive ? " drag-active" : "")}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <strong>{file ? file.name : "Drop a .qif, .qfx, or .ofx file here, or browse"}</strong>
        {!file && "No file selected"}
      </div>
      <div style={{ marginBottom: 24, display: "flex", gap: 8, alignItems: "center" }}>
        <input
          ref={fileInputRef}
          type="file"
          accept=".qif,.qfx,.ofx"
          style={{ display: "none" }}
          onChange={(e) => {
            const selected = e.target.files?.[0];
            if (selected) handleFileSelected(selected);
          }}
        />
        <button className="btn ghost" onClick={() => fileInputRef.current?.click()}>
          Choose file
        </button>

        {detecting && <span className="sub">Scanning file…</span>}

        {!detecting && detection && !showReviewModal && (
          <span className="sub">
            <span className="toast-link" onClick={() => setShowReviewModal(true)}>
              Review and import {file?.name}
            </span>
          </span>
        )}

        {error && <span className="status warn">{error}</span>}
      </div>

      {lastResult && lastResult.length > 0 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div style={{ marginBottom: 8 }}>
            <b>Import complete</b>{" "}
            <span className="sub">
              — {resultTotals.imported} imported · {resultTotals.skipped} duplicate
              {resultTotals.skipped === 1 ? "" : "s"} skipped · {resultTotals.review} need
              {resultTotals.review === 1 ? "s" : ""} attention
            </span>
          </div>
          {lastResult.map((b) => (
            <div key={b.id} className="sub">
              {accountName(b.account_id)}: {b.imported_count} of {b.row_count} imported,{" "}
              {b.skipped_duplicate_count} skipped, {b.needs_review_count} needing attention
            </div>
          ))}
        </div>
      )}

      {showReviewModal && detection && file && (
        <ImportReviewModal
          filename={file.name}
          detection={detection}
          existingAccounts={accounts}
          previewing={previewing}
          submitting={committing}
          onTargetsChange={refreshPreview}
          onClose={() => setShowReviewModal(false)}
          onConfirm={commit}
        />
      )}

      {reviewItems.length > 0 && (
        <>
          <div className="section-title">Needs review ({reviewItems.length})</div>
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Account</th>
                <th>Name</th>
                <th className="right">Amount</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {reviewItems.map((item) => (
                <tr key={item.id}>
                  <td>{item.date}</td>
                  <td>{accountName(item.account_id)}</td>
                  <td>{item.name}</td>
                  <td className="right">${Math.abs(item.amount).toFixed(2)}</td>
                  <td className="ctrl-cell">
                    <button className="btn ghost sm" onClick={() => resolve(item.id, "new")}>
                      New
                    </button>{" "}
                    <button className="btn ghost sm" onClick={() => resolve(item.id, "merge")}>
                      Merge
                    </button>{" "}
                    <button className="btn ghost sm" onClick={() => resolve(item.id, "skip")}>
                      Skip
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <div className="section-title">Recent imports</div>
      <table className="import-log">
        <thead>
          <tr>
            <th>File</th>
            <th>Account</th>
            <th>Rows</th>
            <th>Imported</th>
            <th>Skipped (dup)</th>
            <th>Needs review</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {batches.map((b) => (
            <tr key={b.id}>
              <td>{b.filename}</td>
              <td>{accountName(b.account_id)}</td>
              <td>{b.row_count}</td>
              <td>{b.imported_count}</td>
              <td>{b.skipped_duplicate_count}</td>
              <td>{b.needs_review_count}</td>
              <td>
                {b.needs_review_count > 0 ? (
                  <span className="status warn">{b.needs_review_count} pending</span>
                ) : (
                  <span className="status ok">complete</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

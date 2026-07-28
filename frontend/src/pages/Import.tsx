import type { DragEvent } from "react";
import { useEffect, useRef, useState } from "react";
import { accountsApi } from "../api/accounts";
import { importsApi } from "../api/imports";
import type { Account, ImportBatch, ReviewQueueItem } from "../api/types";

export function Import() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountId, setAccountId] = useState<number | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [reviewItems, setReviewItems] = useState<ReviewQueueItem[]>([]);
  const [uploading, setUploading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function load() {
    importsApi.list().then(setBatches);
    importsApi.reviewItems().then(setReviewItems);
  }

  useEffect(() => {
    accountsApi.list().then((list) => {
      setAccounts(list);
      if (list.length > 0) setAccountId(list[0].id);
    });
    load();
  }, []);

  async function doImport() {
    if (!file || accountId === null) return;
    setUploading(true);
    try {
      await importsApi.upload(accountId, file);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      load();
    } finally {
      setUploading(false);
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
    if (dropped) setFile(dropped);
  }

  const accountName = (id: number) => accounts.find((a) => a.id === id)?.name ?? `#${id}`;

  return (
    <div>
      <h1>Import</h1>
      <p className="sub">Import a QIF statement export. Duplicates are skipped automatically; near-matches are flagged for review.</p>

      <div
        className={"dropzone" + (dragActive ? " drag-active" : "")}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <strong>{file ? file.name : "Drop a .qif file here, or browse"}</strong>
        {!file && "No file selected"}
      </div>
      <div style={{ marginBottom: 24, display: "flex", gap: 8, alignItems: "center" }}>
        <select value={accountId ?? ""} onChange={(e) => setAccountId(Number(e.target.value))}>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
        <input
          ref={fileInputRef}
          type="file"
          accept=".qif"
          style={{ display: "none" }}
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <button className="btn ghost" onClick={() => fileInputRef.current?.click()}>
          Choose file
        </button>
        <button className="btn" onClick={doImport} disabled={!file || accountId === null || uploading}>
          Import
        </button>
      </div>

      {reviewItems.length > 0 && (
        <>
          <div className="section-title">Needs review ({reviewItems.length})</div>
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Name</th>
                <th className="right">Amount</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {reviewItems.map((item) => (
                <tr key={item.id}>
                  <td>{item.date}</td>
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

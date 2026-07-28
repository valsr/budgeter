const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// The key is stored server-side (see routers/settings.py) and can be
// regenerated from Settings → API key. VITE_API_KEY only seeds the very
// first request of a fresh browser profile — once regenerated, the new
// value lives in localStorage so this tab (and future loads) keep working.
const API_KEY_STORAGE_KEY = "budgeter.apiKey";
let apiKey = localStorage.getItem(API_KEY_STORAGE_KEY) ?? import.meta.env.VITE_API_KEY ?? "dev-local-api-key";

export function getApiKey(): string {
  return apiKey;
}

export function setApiKey(key: string): void {
  apiKey = key;
  localStorage.setItem(API_KEY_STORAGE_KEY, key);
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export interface RequestOpts {
  /** Skip the global error toast — for calls whose failures are routine/
   * expected and already handled locally (e.g. a debounced live preview). */
  silent?: boolean;
}

// A global sink for failed requests, set by ToastProvider on mount, so any
// call site gets an "Operation failed" toast for free without individually
// wiring up error handling. Call sites that already show their own inline
// error (SplitModal's split-sum check) still get a toast too — the two only
// double up on genuine backend errors, which is fine; deliberate opt-outs
// use `{ silent: true }`.
type ErrorListener = (message: string) => void;
let errorListener: ErrorListener | null = null;

export function setErrorListener(listener: ErrorListener | null): void {
  errorListener = listener;
}

async function extractErrorMessage(res: Response): Promise<string> {
  const text = await res.text().catch(() => "");
  if (text) {
    try {
      const parsed = JSON.parse(text);
      if (typeof parsed?.detail === "string") return parsed.detail;
      if (Array.isArray(parsed?.detail)) {
        // FastAPI/pydantic validation error shape: [{loc, msg, type}, ...]
        const messages = parsed.detail.map((d: { msg?: string }) => d.msg).filter(Boolean);
        if (messages.length > 0) return messages.join("; ");
      }
    } catch {
      // Not JSON — fall through to the raw response text.
    }
  }
  return text || res.statusText || `Request failed (${res.status})`;
}

async function rawFetch(path: string, init: RequestInit = {}, opts: RequestOpts = {}): Promise<Response> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${apiKey}`,
      ...init.headers,
    },
  });
  if (!res.ok) {
    const message = await extractErrorMessage(res);
    if (!opts.silent) errorListener?.(message);
    throw new ApiError(res.status, message);
  }
  return res;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}, opts: RequestOpts = {}): Promise<T> {
  const res = await rawFetch(
    path,
    {
      ...init,
      headers: {
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...init.headers,
      },
    },
    opts,
  );
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// For multipart uploads: do NOT set Content-Type — the browser must set it
// (with the multipart boundary) when the body is a FormData instance.
export async function apiUpload<T>(path: string, formData: FormData, opts: RequestOpts = {}): Promise<T> {
  const res = await rawFetch(path, { method: "POST", body: formData }, opts);
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function apiDownload(path: string): Promise<{ blob: Blob; filename: string | null }> {
  const res = await rawFetch(path);
  const disposition = res.headers.get("content-disposition") ?? "";
  const match = /filename="?([^";]+)"?/.exec(disposition);
  return { blob: await res.blob(), filename: match ? match[1] : null };
}

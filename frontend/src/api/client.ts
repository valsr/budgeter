const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

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

// Called when the server says the session is gone (expired, logged out
// elsewhere, account disabled), so AuthProvider can drop back to the login
// screen from wherever the app happened to be.
type UnauthorizedListener = () => void;
let unauthorizedListener: UnauthorizedListener | null = null;

export function setUnauthorizedListener(listener: UnauthorizedListener | null): void {
  unauthorizedListener = listener;
}

// The one endpoint where a 401 means "wrong credentials", not "no session".
const LOGIN_PATH = "/api/auth/login";

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
  // The session lives in an httpOnly cookie; "include" sends it to the API
  // even when the dev server and the API are on different ports.
  const res = await fetch(`${API_BASE_URL}${path}`, { ...init, credentials: "include" });
  if (!res.ok) {
    const message = await extractErrorMessage(res);
    if (res.status === 401 && path !== LOGIN_PATH) {
      // No toast: the login screen that replaces the app says it all.
      unauthorizedListener?.();
    } else if (!opts.silent) {
      errorListener?.(message);
    }
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

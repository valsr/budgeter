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

async function rawFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${apiKey}`,
      ...init.headers,
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(res.status, text || res.statusText);
  }
  return res;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await rawFetch(path, {
    ...init,
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// For multipart uploads: do NOT set Content-Type — the browser must set it
// (with the multipart boundary) when the body is a FormData instance.
export async function apiUpload<T>(path: string, formData: FormData): Promise<T> {
  const res = await rawFetch(path, { method: "POST", body: formData });
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function apiDownload(path: string): Promise<{ blob: Blob; filename: string | null }> {
  const res = await rawFetch(path);
  const disposition = res.headers.get("content-disposition") ?? "";
  const match = /filename="?([^";]+)"?/.exec(disposition);
  return { blob: await res.blob(), filename: match ? match[1] : null };
}

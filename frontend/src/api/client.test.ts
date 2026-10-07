import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch, setErrorListener, setUnauthorizedListener } from "./client";

const fetchMock = vi.fn();

function respond(status: number, body: unknown) {
  fetchMock.mockResolvedValue(new Response(JSON.stringify(body), { status }));
}

describe("api client", () => {
  const onError = vi.fn();
  const onUnauthorized = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockReset();
    onError.mockReset();
    onUnauthorized.mockReset();
    setErrorListener(onError);
    setUnauthorizedListener(onUnauthorized);
  });

  afterEach(() => {
    setErrorListener(null);
    setUnauthorizedListener(null);
    vi.unstubAllGlobals();
  });

  it("sends credentials and no Authorization header", async () => {
    respond(200, []);
    await apiFetch("/api/accounts");
    const [, init] = fetchMock.mock.calls[0];
    expect(init.credentials).toBe("include");
    expect(new Headers(init.headers).has("Authorization")).toBe(false);
  });

  it("notifies the unauthorized listener on 401 without a toast", async () => {
    respond(401, { detail: "Not authenticated" });
    await expect(apiFetch("/api/accounts")).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
    expect(onError).not.toHaveBeenCalled();
  });

  it("treats a 401 from the login endpoint as a failed login, not a lost session", async () => {
    respond(401, { detail: "Invalid username or password" });
    await expect(apiFetch("/api/auth/login", { method: "POST" }, { silent: true })).rejects.toMatchObject({
      status: 401,
      message: "Invalid username or password",
    });
    expect(onUnauthorized).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
  });

  it("still toasts other errors", async () => {
    respond(409, { detail: "Username is already taken" });
    await expect(apiFetch("/api/admin/users", { method: "POST" })).rejects.toBeInstanceOf(ApiError);
    expect(onError).toHaveBeenCalledWith("Username is already taken");
    expect(onUnauthorized).not.toHaveBeenCalled();
  });
});

import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetch = vi.fn();

vi.mock("./client", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

import { rulesApi, setCategorizationChangedListener } from "./rules";

describe("rulesApi categorization-changed notifications", () => {
  beforeEach(() => {
    apiFetch.mockReset();
    setCategorizationChangedListener(null);
  });

  it("notifies the subscribed listener after create", async () => {
    apiFetch.mockResolvedValue({ id: 1 });
    const listener = vi.fn();
    setCategorizationChangedListener(listener);

    await rulesApi.create({ match_type: "all", conditions: [], target_category_id: 1 });

    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("notifies the subscribed listener after update", async () => {
    apiFetch.mockResolvedValue({ id: 1 });
    const listener = vi.fn();
    setCategorizationChangedListener(listener);

    await rulesApi.update(1, { target_category_id: 2 });

    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("notifies the subscribed listener after learn", async () => {
    apiFetch.mockResolvedValue({ rule: { id: 1 }, confirmed_count: 0, confirmed_transaction_ids: [] });
    const listener = vi.fn();
    setCategorizationChangedListener(listener);

    await rulesApi.learn({ match_type: "all", conditions: [], target_category_id: 1 });

    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("does not notify for calls that don't change categorization", async () => {
    apiFetch.mockResolvedValue([]);
    const listener = vi.fn();
    setCategorizationChangedListener(listener);

    await rulesApi.list();
    await rulesApi.reorder([1, 2]);

    expect(listener).not.toHaveBeenCalled();
  });

  it("does nothing when no listener is subscribed", async () => {
    apiFetch.mockResolvedValue({ id: 1 });
    await expect(rulesApi.create({ match_type: "all", conditions: [], target_category_id: 1 })).resolves.toBeTruthy();
  });

  it("stops notifying after unsubscribing", async () => {
    apiFetch.mockResolvedValue({ id: 1 });
    const listener = vi.fn();
    setCategorizationChangedListener(listener);
    setCategorizationChangedListener(null);

    await rulesApi.create({ match_type: "all", conditions: [], target_category_id: 1 });

    expect(listener).not.toHaveBeenCalled();
  });
});

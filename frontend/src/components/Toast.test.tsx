import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "../api/client";
import type { Category, LearnCheckResponse, Rule } from "../api/types";
import { ToastProvider, useLearnCheck } from "./Toast";

const learnCheck = vi.fn<(transactionId: number) => Promise<LearnCheckResponse>>();
const getRule = vi.fn();
const previewMatches = vi.fn();
const listCategories = vi.fn();

vi.mock("../api/rules", () => ({
  rulesApi: {
    learnCheck: (...args: unknown[]) => learnCheck(...(args as [number])),
    get: (...args: unknown[]) => getRule(...args),
    previewMatches: (...args: unknown[]) => previewMatches(...args),
    create: vi.fn(),
    update: vi.fn(),
    learn: vi.fn(),
    remove: vi.fn(),
    reorder: vi.fn(),
    list: vi.fn(),
  },
}));

vi.mock("../api/categories", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/categories")>()),
  categoriesApi: {
    list: (...args: unknown[]) => listCategories(...args),
  },
}));

const categories: Category[] = [
  {
    id: 1,
    name: "personal",
    parent_id: null,
    color: "#111",
    sort_order: 0,
    archived_at: null,
    children: [{ id: 2, name: "dining", parent_id: 1, color: "#222", sort_order: 0, archived_at: null, children: [] }],
  },
];

const rule: Rule = {
  id: 5,
  match_type: "all",
  priority: 0,
  target_category_id: 2,
  conditions: [{ id: 50, field: "name", operator: "contains", value: "github" }],
};

function Trigger({ id }: { id: number }) {
  const check = useLearnCheck();
  return (
    <button onClick={() => check(id)}>trigger-{id}</button>
  );
}

function renderWithTriggers(ids: number[]) {
  render(
    <ToastProvider>
      {ids.map((id) => (
        <Trigger key={id} id={id} />
      ))}
    </ToastProvider>,
  );
}

describe("Toast", () => {
  beforeEach(() => {
    learnCheck.mockReset();
    getRule.mockReset();
    previewMatches.mockReset();
    listCategories.mockReset();
    listCategories.mockResolvedValue(categories);
    previewMatches.mockResolvedValue({ count: 0, sample: [] });
  });

  it("shows nothing for 'covered' or 'none' statuses", async () => {
    learnCheck.mockResolvedValue({ status: "covered", conflict: null, suggestion: null });
    renderWithTriggers([1]);
    fireEvent.click(screen.getByText("trigger-1"));
    await waitFor(() => expect(learnCheck).toHaveBeenCalledWith(1));
    expect(screen.queryByText(/Possible rule found/)).not.toBeInTheDocument();
    expect(screen.queryByText(/already categorizes/)).not.toBeInTheDocument();
  });

  it("shows a conflict toast, and its close button removes only that toast", async () => {
    learnCheck.mockResolvedValue({
      status: "conflict",
      conflict: { rule_id: 5, rule_summary: "name contains 'github'", matched_category_id: 2, assigned_category_id: 3 },
      suggestion: null,
    });
    renderWithTriggers([1]);
    fireEvent.click(screen.getByText("trigger-1"));

    const closeBtn = await screen.findByText("✕");
    expect(screen.getByText(/already categorizes/)).toBeInTheDocument();

    fireEvent.click(closeBtn);
    expect(screen.queryByText(/already categorizes/)).not.toBeInTheDocument();
  });

  it("conflict toast's 'View rule' opens RuleModal in plain edit mode and dismisses the toast", async () => {
    learnCheck.mockResolvedValue({
      status: "conflict",
      conflict: { rule_id: 5, rule_summary: "name contains 'github'", matched_category_id: 2, assigned_category_id: 3 },
      suggestion: null,
    });
    getRule.mockResolvedValue(rule);
    renderWithTriggers([1]);
    fireEvent.click(screen.getByText("trigger-1"));

    fireEvent.click(await screen.findByText("View rule"));

    await screen.findByText("Edit rule");
    expect(getRule).toHaveBeenCalledWith(5);
    expect(screen.queryByText(/already categorizes/)).not.toBeInTheDocument();
  });

  it("shows a suggestion toast; Add opens RuleModal pre-filled (learned flow) and dismisses the toast", async () => {
    learnCheck.mockResolvedValue({
      status: "suggestion",
      conflict: null,
      suggestion: {
        tier: 1,
        match_type: "all",
        conditions: [{ field: "name", operator: "contains", value: "mcdonalds" }],
        target_category_id: 2,
      },
    });
    renderWithTriggers([1]);
    fireEvent.click(screen.getByText("trigger-1"));

    expect(await screen.findByText(/Possible rule found/)).toBeInTheDocument();

    fireEvent.click(screen.getByText("Add"));

    await screen.findByText("Add learned rule");
    expect(screen.queryByText(/Possible rule found/)).not.toBeInTheDocument();
    expect(screen.getByDisplayValue("mcdonalds")).toBeInTheDocument();
  });

  it("stacks multiple toasts from independent triggers", async () => {
    learnCheck.mockImplementation(async (id: number) => ({
      status: "suggestion",
      conflict: null,
      suggestion: {
        tier: 1,
        match_type: "all",
        conditions: [{ field: "name", operator: "contains", value: `merchant-${id}` }],
        target_category_id: 2,
      },
    }));
    renderWithTriggers([1, 2]);
    fireEvent.click(screen.getByText("trigger-1"));
    fireEvent.click(screen.getByText("trigger-2"));

    await screen.findByText(/merchant-1/);
    await screen.findByText(/merchant-2/);
    expect(screen.getAllByText("Add")).toHaveLength(2);
  });

  describe("global error toast", () => {
    afterEach(() => {
      vi.unstubAllGlobals();
    });

    it("shows 'Operation failed: <detail>' for any failed API call anywhere in the app, dismissible", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Account 5 not found" }), { status: 404 })),
      );
      renderWithTriggers([]);

      await expect(apiFetch("/api/whatever")).rejects.toThrow("Account 5 not found");

      const closeBtn = await screen.findByText("✕");
      expect(screen.getByText("Operation failed: Account 5 not found")).toBeInTheDocument();

      fireEvent.click(closeBtn);
      expect(screen.queryByText(/Operation failed/)).not.toBeInTheDocument();
    });

    it("does not toast for calls made with { silent: true }", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "nope" }), { status: 422 })),
      );
      renderWithTriggers([]);

      await expect(apiFetch("/api/whatever", {}, { silent: true })).rejects.toThrow("nope");

      // give any (incorrect) toast a chance to appear before asserting absence
      await new Promise((r) => setTimeout(r, 0));
      expect(screen.queryByText(/Operation failed/)).not.toBeInTheDocument();
    });
  });
});

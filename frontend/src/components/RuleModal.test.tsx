import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Account, Category, Rule } from "../api/types";
import { RuleModal } from "./RuleModal";

const create = vi.fn();
const update = vi.fn();
const learn = vi.fn();
const previewMatches = vi.fn();
const listAccounts = vi.fn();

vi.mock("../api/accounts", () => ({
  accountsApi: { list: () => listAccounts() },
}));

vi.mock("../api/rules", () => ({
  rulesApi: {
    create: (...args: unknown[]) => create(...args),
    update: (...args: unknown[]) => update(...args),
    learn: (...args: unknown[]) => learn(...args),
    previewMatches: (...args: unknown[]) => previewMatches(...args),
  },
}));

const categories: Category[] = [
  {
    id: 1,
    name: "personal",
    parent_id: null,
    color: "#111",
    sort_order: 0,
    archived_at: null, is_income: false,
    children: [{ id: 2, name: "dining", parent_id: 1, color: "#222", sort_order: 0, archived_at: null, is_income: false, children: [] }],
  },
];

const accounts: Account[] = [
  { id: 7, name: "Main checking", account_number: null, type: "asset", opening_balance: 0, color: "#111", balance: 0 },
  { id: 8, name: "Visa", account_number: null, type: "liability", opening_balance: 0, color: "#222", balance: 0 },
];

const rule: Rule = {
  id: 5,
  match_type: "all",
  priority: 0,
  target_category_id: 2,
  conditions: [{ id: 50, field: "name", operator: "contains", value: "github" }],
};

describe("RuleModal", () => {
  beforeEach(() => {
    create.mockReset().mockResolvedValue(rule);
    update.mockReset().mockResolvedValue(rule);
    learn.mockReset().mockResolvedValue({ rule, confirmed_count: 0, confirmed_transaction_ids: [] });
    previewMatches.mockReset().mockResolvedValue({ count: 0, matches: [] });
    listAccounts.mockReset().mockResolvedValue(accounts);
  });

  it("plain new mode calls create, not learn (regression guard for the extraction)", async () => {
    const onSaved = vi.fn();
    render(<RuleModal mode="new" categories={categories} onClose={() => {}} onSaved={onSaved} />);

    fireEvent.change(screen.getByPlaceholderText("value"), { target: { value: "spotify" } });
    fireEvent.click(screen.getByText("Save rule"));

    await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
    expect(learn).not.toHaveBeenCalled();
    expect(create).toHaveBeenCalledWith({
      match_type: "all",
      conditions: [{ field: "name", operator: "contains", value: "spotify" }],
      target_category_id: 2,
    });
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });

  it("plain edit mode calls update with the rule id", async () => {
    const onSaved = vi.fn();
    render(<RuleModal mode="edit" rule={rule} categories={categories} onClose={() => {}} onSaved={onSaved} />);

    fireEvent.click(screen.getByText("Save rule"));

    await waitFor(() => expect(update).toHaveBeenCalledWith(5, expect.objectContaining({ target_category_id: 2 })));
    expect(create).not.toHaveBeenCalled();
    expect(learn).not.toHaveBeenCalled();
  });

  it("learnedFlow pre-fills from `initial` and calls learn (not create) on save", async () => {
    const onSaved = vi.fn();
    render(
      <RuleModal
        mode="new"
        categories={categories}
        learnedFlow
        initial={{
          matchType: "all",
          conditions: [{ field: "name", operator: "contains", value: "mcdonalds" }],
          targetCategoryId: 2,
        }}
        onClose={() => {}}
        onSaved={onSaved}
      />,
    );

    expect(screen.getByDisplayValue("mcdonalds")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Add rule"));

    await waitFor(() => expect(learn).toHaveBeenCalledTimes(1));
    expect(create).not.toHaveBeenCalled();
    expect(update).not.toHaveBeenCalled();
    expect(learn).toHaveBeenCalledWith({
      match_type: "all",
      conditions: [{ field: "name", operator: "contains", value: "mcdonalds" }],
      target_category_id: 2,
    });
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });

  it("live preview calls previewMatches on condition change and renders a table of matches", async () => {
    previewMatches.mockResolvedValue({
      count: 3,
      matches: [{ id: 1, date: "2026-01-01", name: "McDonalds #1", amount: -5 }],
    });
    render(<RuleModal mode="new" categories={categories} onClose={() => {}} onSaved={() => {}} />);

    fireEvent.change(screen.getByPlaceholderText("value"), { target: { value: "mcdonalds" } });

    await waitFor(() => expect(previewMatches).toHaveBeenCalledTimes(1), { timeout: 1000 });
    expect(previewMatches).toHaveBeenCalledWith({
      match_type: "all",
      conditions: [{ field: "name", operator: "contains", value: "mcdonalds" }],
      target_category_id: 2,
    });
    await screen.findByText(/Matches 3 currently-uncategorized transaction/);
    expect(await screen.findByText("McDonalds #1")).toBeInTheDocument();
    expect(screen.getByText("Showing 1–1 of 1")).toBeInTheDocument();
  });

  it("paginates the preview table 10 rows at a time", async () => {
    const matches = Array.from({ length: 12 }, (_, i) => ({
      id: i + 1,
      date: "2026-01-01",
      name: `McDonalds #${i + 1}`,
      amount: -5,
    }));
    previewMatches.mockResolvedValue({ count: 12, matches });
    render(<RuleModal mode="new" categories={categories} onClose={() => {}} onSaved={() => {}} />);

    fireEvent.change(screen.getByPlaceholderText("value"), { target: { value: "mcdonalds" } });

    await screen.findByText("McDonalds #1");
    expect(screen.getByText("McDonalds #10")).toBeInTheDocument();
    expect(screen.queryByText("McDonalds #11")).not.toBeInTheDocument();
    expect(screen.getByText("Showing 1–10 of 12")).toBeInTheDocument();

    fireEvent.click(screen.getByText("›"));

    await screen.findByText("McDonalds #11");
    expect(screen.getByText("McDonalds #12")).toBeInTheDocument();
    expect(screen.queryByText("McDonalds #1")).not.toBeInTheDocument();
    expect(screen.getByText("Showing 11–12 of 12")).toBeInTheDocument();
  });

  it("picks an account by name for an account condition instead of asking for a raw id", async () => {
    const onSaved = vi.fn();
    render(<RuleModal mode="new" categories={categories} onClose={() => {}} onSaved={onSaved} />);
    await waitFor(() => expect(listAccounts).toHaveBeenCalled());

    fireEvent.change(screen.getByDisplayValue("Name"), { target: { value: "account" } });

    // Free-text value input is replaced by the account picker, and the
    // operator collapses to the only one an account id supports.
    expect(screen.queryByPlaceholderText("value")).not.toBeInTheDocument();
    const picker = screen.getByLabelText("Account") as HTMLSelectElement;
    expect(picker.value).toBe("7"); // defaulted, not left blank
    expect(screen.getByText("Visa")).toBeInTheDocument();

    fireEvent.change(picker, { target: { value: "8" } });
    fireEvent.click(screen.getByText("Save rule"));

    await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
    expect(create).toHaveBeenCalledWith({
      match_type: "all",
      conditions: [{ field: "account", operator: "equals", value: "8" }],
      target_category_id: 2,
    });
  });

  it("clears a carried-over value when switching a condition away from account", async () => {
    render(<RuleModal mode="new" categories={categories} onClose={() => {}} onSaved={() => {}} />);
    await waitFor(() => expect(listAccounts).toHaveBeenCalled());

    fireEvent.change(screen.getByDisplayValue("Name"), { target: { value: "account" } });
    fireEvent.change(screen.getByDisplayValue("Account"), { target: { value: "name" } });

    // An account id left in a name condition would silently match nothing.
    expect((screen.getByPlaceholderText("value") as HTMLInputElement).value).toBe("");
  });

  it("keeps Save disabled until every condition has a value", async () => {
    render(<RuleModal mode="new" categories={categories} onClose={() => {}} onSaved={() => {}} />);
    expect(screen.getByText("Save rule")).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText("value"), { target: { value: "spotify" } });
    expect(screen.getByText("Save rule")).not.toBeDisabled();
  });

  it("does not call previewMatches while a condition value is empty", async () => {
    render(<RuleModal mode="new" categories={categories} onClose={() => {}} onSaved={() => {}} />);
    await new Promise((r) => setTimeout(r, 500));
    expect(previewMatches).not.toHaveBeenCalled();
  });
});

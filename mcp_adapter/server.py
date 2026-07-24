"""Thin MCP adapter over the Budgeter REST API.

Every tool here is a direct pass-through to one REST endpoint — no
business logic lives in this adapter (docs/requirements.md §6). It's
meant to give a Claude skill/agent read access to accounts, transactions,
and categories, plus the one write path the spec calls for: submitting
on-demand AI category suggestions (docs/requirements.md §3.2).
"""

from typing import Any

from mcp.server.fastmcp import FastMCP

from client import BudgeterClient

mcp = FastMCP("budgeter")
client = BudgeterClient()


@mcp.tool()
async def list_accounts() -> Any:
    """List all accounts with their name, type, and current running balance."""
    return await client.get("/api/accounts")


@mcp.tool()
async def list_categories(include_archived: bool = False) -> Any:
    """List the category tree (parent -> children), in the user's configured display order."""
    return await client.get("/api/categories", params={"include_archived": include_archived})


@mcp.tool()
async def list_transactions(
    account_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    name_contains: str | None = None,
    category_id: int | None = None,
    page: int = 1,
) -> Any:
    """List transactions with optional filters (server-side paginated, 100/page).

    date_from/date_to are ISO dates (YYYY-MM-DD). category_id filtering
    includes that category's children (rollup-aware).
    """
    params = {
        k: v
        for k, v in {
            "account_id": account_id,
            "date_from": date_from,
            "date_to": date_to,
            "amount_min": amount_min,
            "amount_max": amount_max,
            "name_contains": name_contains,
            "category_id": category_id,
            "page": page,
        }.items()
        if v is not None
    }
    return await client.get("/api/transactions", params=params)


@mcp.tool()
async def get_transaction(transaction_id: int) -> Any:
    """Get one transaction, including its splits and any pending suggestion."""
    return await client.get(f"/api/transactions/{transaction_id}")


@mcp.tool()
async def list_uncategorized_for_ai() -> Any:
    """List transactions eligible for an AI category suggestion.

    Eligible means: a normal (non-transfer) transaction with a single
    split that has no confirmed category yet. Use this to find work
    before calling suggest_categories.
    """
    return await client.get("/api/ai/uncategorized")


@mcp.tool()
async def suggest_categories(suggestions: list[dict]) -> Any:
    """Submit AI-proposed categories for uncategorized transactions.

    AI categorization is on-demand only and must be explicitly invoked —
    it never runs automatically (docs/requirements.md §3.2). Each item in
    `suggestions` is {"transaction_id": int, "split_id": int,
    "category_id": int}. Suggestions render in the app the same way a
    rule's suggestion does (dashed border, accept/reject) — this call
    does not confirm the category itself, only proposes it. A split
    that's already confirmed is skipped rather than overwritten.
    """
    return await client.post("/api/ai/suggest", json={"suggestions": suggestions})


@mcp.tool()
async def list_rules() -> Any:
    """List categorization rules in evaluation order (first match wins)."""
    return await client.get("/api/rules")


@mcp.tool()
async def list_budgets() -> Any:
    """List saved budgets (each is also the definition of a named report)."""
    return await client.get("/api/budgets")


@mcp.tool()
async def get_budget_report(budget_id: int, year: int, through_month: int) -> Any:
    """Get a budget's Jan-through-`through_month` report: rows are categories
    (parent rows are derived rollups of their children), each with a
    budgeted/actual figure per month and a cumulative YTD diff.
    """
    return await client.get(
        f"/api/budgets/{budget_id}/report", params={"year": year, "through_month": through_month}
    )


@mcp.tool()
async def get_overview(year: int, through_month: int) -> Any:
    """Get the Overview screen's category table: every non-archived leaf
    category (and its parent rollups) with YTD budgeted/actual/balance,
    regardless of which saved budget it belongs to.
    """
    return await client.get("/api/overview", params={"year": year, "through_month": through_month})


@mcp.tool()
async def uncategorized_count() -> Any:
    """Count of transactions with no confirmed category (matches the Overview banner)."""
    return await client.get("/api/transactions/uncategorized-count")


if __name__ == "__main__":
    mcp.run()

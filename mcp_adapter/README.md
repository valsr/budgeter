# budgeter MCP adapter

A thin [MCP](https://modelcontextprotocol.io) server that wraps the Budgeter REST API so Claude (or any MCP client) can browse accounts/transactions/categories and submit on-demand AI category suggestions, per [docs/requirements.md](../docs/requirements.md) §3.2 and §6.

No business logic lives here — every tool in `server.py` is a direct pass-through to one REST endpoint via the thin `BudgeterClient` in `client.py`. The core app does not speak MCP natively; this is a separate, optional process.

## Setup

```bash
cd mcp_adapter
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Config is read from environment variables (prefix `BUDGETER_MCP_`) or a `mcp_adapter/.env` file:

- `BUDGETER_MCP_API_BASE_URL` — where the Budgeter backend is running (defaults to `http://localhost:8000`)
- `BUDGETER_MCP_API_KEY` — the backend's bearer token, i.e. whatever `BUDGETER_API_KEY` the backend is configured with (defaults to `dev-local-api-key`, matching the backend's dev default)

The Budgeter backend must be running (`uvicorn app.main:app` — see the top-level [README](../README.md)) for this adapter to do anything useful.

## Running

The server speaks MCP over stdio — it's meant to be launched by an MCP client, not run standalone. To register it with Claude Code:

```bash
claude mcp add budgeter -- /path/to/mcp_adapter/.venv/bin/python /path/to/mcp_adapter/server.py
```

Or add it manually to your MCP client's config (e.g. Claude Desktop's `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "budgeter": {
      "command": "/path/to/mcp_adapter/.venv/bin/python",
      "args": ["/path/to/mcp_adapter/server.py"],
      "env": { "BUDGETER_MCP_API_KEY": "your-api-key" }
    }
  }
}
```

## Tools

| Tool | REST endpoint | Purpose |
|---|---|---|
| `list_accounts` | `GET /api/accounts` | Accounts with balances |
| `list_categories` | `GET /api/categories` | Category tree, in display order |
| `list_transactions` | `GET /api/transactions` | Filtered, paginated transaction list |
| `get_transaction` | `GET /api/transactions/{id}` | One transaction with splits |
| `list_uncategorized_for_ai` | `GET /api/ai/uncategorized` | Transactions eligible for an AI suggestion |
| `suggest_categories` | `POST /api/ai/suggest` | Submit proposed categories (the on-demand AI categorization entry point) |
| `list_rules` | `GET /api/rules` | Categorization rules, in evaluation order |
| `list_budgets` | `GET /api/budgets` | Saved budgets/reports |
| `get_budget_report` | `GET /api/budgets/{id}/report` | A budget's Jan→month report |
| `get_overview` | `GET /api/overview` | The Overview screen's global category rollup |
| `uncategorized_count` | `GET /api/transactions/uncategorized-count` | Count for the Overview banner |

`suggest_categories` is the one write path. It never confirms a category on its own — it sets `suggested_category_id` on the split, which then renders in the app through the same accept/reject suggestion UI a rule's suggestion uses, and never overwrites a split that already has a confirmed category.

## Testing

```bash
pytest
```

Unit tests (`test_client.py`) mock the HTTP layer with `respx` and cover auth headers, parameter passthrough, and error handling. `smoke_test.py` is a manual, non-pytest script that spawns the real server as an MCP subprocess and calls tools against a live backend — run it directly when you want to verify the whole stack end-to-end (needs the backend running with at least one account and category).

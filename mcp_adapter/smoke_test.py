"""Manual live smoke test: spawns server.py as a real MCP subprocess and
calls tools against a running Budgeter backend, including the
suggest_categories write path. Not part of the pytest suite (it needs a
live backend with at least one account, category, and uncategorized
transaction) — run directly:

    BUDGETER_MCP_API_KEY=<your key> .venv/bin/python smoke_test.py
"""

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(command=sys.executable, args=["server.py"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Tools:", [t.name for t in tools.tools])

            accounts = await session.call_tool("list_accounts", {})
            first_account = json.loads(accounts.content[0].text)
            print("list_accounts ->", first_account)
            assert "id" in first_account, "expected at least one account"

            categories = await session.call_tool("list_categories", {})
            first_category = json.loads(categories.content[0].text)
            print("list_categories ->", first_category)

            uncategorized = await session.call_tool("list_uncategorized_for_ai", {})
            if uncategorized.content:
                txn = json.loads(uncategorized.content[0].text)
                print("list_uncategorized_for_ai ->", txn)

                result = await session.call_tool(
                    "suggest_categories",
                    {
                        "suggestions": [
                            {
                                "transaction_id": txn["id"],
                                "split_id": txn["splits"][0]["id"],
                                "category_id": first_category["id"],
                            }
                        ]
                    },
                )
                print("suggest_categories ->", result.content[0].text)

                after = await session.call_tool("get_transaction", {"transaction_id": txn["id"]})
                after_txn = json.loads(after.content[0].text)
                print("after suggest ->", after_txn)
                assert after_txn["splits"][0]["suggested_category_id"] == first_category["id"]
            else:
                print("(no uncategorized transactions to test suggest_categories against)")

            print("\nSMOKE TEST PASSED")


if __name__ == "__main__":
    asyncio.run(main())

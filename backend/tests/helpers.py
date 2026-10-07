"""Helpers shared across test modules."""

import sqlite3


def make_account(client, name: str) -> int:
    resp = client.post("/api/accounts", json={"name": name, "type": "asset"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def account_names(client) -> list[str]:
    return [a["name"] for a in client.get("/api/accounts").json()]


def tables(path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()

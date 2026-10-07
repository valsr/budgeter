"""Shared by the tests that drive the app through a logged-in client."""


def make_account(client, name: str) -> int:
    resp = client.post("/api/accounts", json={"name": name, "type": "asset"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def account_names(client) -> list[str]:
    return [a["name"] for a in client.get("/api/accounts").json()]

import pytest


@pytest.fixture()
def account_id(client, auth_headers):
    return client.post(
        "/api/accounts", json={"name": "Main", "type": "asset", "opening_balance": 1000}, headers=auth_headers
    ).json()["id"]


@pytest.fixture()
def category_id(client, auth_headers):
    return client.post("/api/categories", json={"name": "personal"}, headers=auth_headers).json()["id"]


def test_requires_auth(client):
    resp = client.get("/api/ai/uncategorized")
    assert resp.status_code == 401


def test_list_uncategorized(client, auth_headers, account_id, category_id):
    client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "Amazon", "splits": [{"amount": -10.0}]},
        headers=auth_headers,
    )
    client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "date": "2026-01-02",
            "name": "Costco",
            "splits": [{"category_id": category_id, "amount": -10.0}],
        },
        headers=auth_headers,
    )
    resp = client.get("/api/ai/uncategorized", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["name"] == "Amazon"


def test_suggest_endpoint(client, auth_headers, account_id, category_id):
    txn = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "Amazon", "splits": [{"amount": -10.0}]},
        headers=auth_headers,
    ).json()
    split_id = txn["splits"][0]["id"]

    resp = client.post(
        "/api/ai/suggest",
        json={"suggestions": [{"transaction_id": txn["id"], "split_id": split_id, "category_id": category_id}]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json() == {"applied": 1, "skipped": []}

    refreshed = client.get(f"/api/transactions/{txn['id']}", headers=auth_headers).json()
    assert refreshed["splits"][0]["suggested_category_id"] == category_id
    assert refreshed["splits"][0]["suggestion_source"] == "ai"


def test_suggest_unknown_transaction_404(client, auth_headers, category_id):
    resp = client.post(
        "/api/ai/suggest",
        json={"suggestions": [{"transaction_id": 999, "split_id": 1, "category_id": category_id}]},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_suggest_unknown_category_404(client, auth_headers, account_id):
    txn = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "Amazon", "splits": [{"amount": -10.0}]},
        headers=auth_headers,
    ).json()
    resp = client.post(
        "/api/ai/suggest",
        json={"suggestions": [{"transaction_id": txn["id"], "split_id": txn["splits"][0]["id"], "category_id": 999}]},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_suggest_skips_confirmed_split(client, auth_headers, account_id, category_id):
    other_cat = client.post("/api/categories", json={"name": "shared"}, headers=auth_headers).json()["id"]
    txn = client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "date": "2026-01-01",
            "name": "Amazon",
            "splits": [{"category_id": category_id, "amount": -10.0}],
        },
        headers=auth_headers,
    ).json()
    resp = client.post(
        "/api/ai/suggest",
        json={
            "suggestions": [
                {"transaction_id": txn["id"], "split_id": txn["splits"][0]["id"], "category_id": other_cat}
            ]
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json() == {"applied": 0, "skipped": [txn["id"]]}

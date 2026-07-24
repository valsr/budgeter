import pytest


@pytest.fixture()
def account_id(client, auth_headers):
    resp = client.post(
        "/api/accounts",
        json={"name": "Main checking", "type": "asset", "opening_balance": 1000},
        headers=auth_headers,
    )
    return resp.json()["id"]


@pytest.fixture()
def other_account_id(client, auth_headers):
    resp = client.post(
        "/api/accounts",
        json={"name": "Shared credit card", "type": "liability", "opening_balance": -600},
        headers=auth_headers,
    )
    return resp.json()["id"]


@pytest.fixture()
def category_id(client, auth_headers):
    resp = client.post("/api/categories", json={"name": "shared"}, headers=auth_headers)
    return resp.json()["id"]


def test_requires_auth(client):
    resp = client.get("/api/transactions")
    assert resp.status_code == 401


def test_create_and_get_transaction(client, auth_headers, account_id, category_id):
    resp = client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "date": "2026-01-05",
            "name": "Costco",
            "splits": [{"category_id": category_id, "amount": -88.40}],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    txn = resp.json()
    assert txn["type"] == "normal"

    resp = client.get(f"/api/transactions/{txn['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Costco"


def test_create_transaction_unknown_account_404(client, auth_headers):
    resp = client.post(
        "/api/transactions",
        json={"account_id": 999, "date": "2026-01-01", "name": "x", "splits": [{"amount": -1.0}]},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_create_transaction_bad_splits_422(client, auth_headers, account_id, category_id):
    resp = client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "date": "2026-01-01",
            "name": "x",
            "splits": [
                {"category_id": category_id, "amount": -1.0},
                {"category_id": category_id, "amount": -2.0},
            ],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_get_missing_transaction_404(client, auth_headers):
    resp = client.get("/api/transactions/999", headers=auth_headers)
    assert resp.status_code == 404


def test_update_transaction_details(client, auth_headers, account_id):
    created = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "x", "splits": [{"amount": -1.0}]},
        headers=auth_headers,
    ).json()
    resp = client.patch(
        f"/api/transactions/{created['id']}", json={"name": "y"}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "y"


def test_update_missing_transaction_404(client, auth_headers):
    resp = client.patch("/api/transactions/999", json={"name": "y"}, headers=auth_headers)
    assert resp.status_code == 404


def test_update_splits(client, auth_headers, account_id, category_id):
    created = client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "date": "2026-01-01",
            "name": "Costco",
            "splits": [{"category_id": category_id, "amount": -88.40}],
        },
        headers=auth_headers,
    ).json()
    c2 = client.post("/api/categories", json={"name": "household"}, headers=auth_headers).json()

    resp = client.put(
        f"/api/transactions/{created['id']}/splits",
        json={"splits": [{"category_id": category_id, "amount": -60.0}, {"category_id": c2["id"], "amount": -28.40}]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()["splits"]) == 2


def test_update_splits_mismatched_total_422(client, auth_headers, account_id, category_id):
    created = client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "date": "2026-01-01",
            "name": "Costco",
            "splits": [{"category_id": category_id, "amount": -88.40}],
        },
        headers=auth_headers,
    ).json()
    resp = client.put(
        f"/api/transactions/{created['id']}/splits",
        json={"splits": [{"category_id": category_id, "amount": -50.0}]},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_update_splits_missing_transaction_404(client, auth_headers, category_id):
    resp = client.put(
        "/api/transactions/999/splits",
        json={"splits": [{"category_id": category_id, "amount": -1.0}]},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_delete_transaction(client, auth_headers, account_id):
    created = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "x", "splits": [{"amount": -1.0}]},
        headers=auth_headers,
    ).json()
    resp = client.delete(f"/api/transactions/{created['id']}", headers=auth_headers)
    assert resp.status_code == 204
    assert client.get(f"/api/transactions/{created['id']}", headers=auth_headers).status_code == 404


def test_delete_missing_transaction_404(client, auth_headers):
    resp = client.delete("/api/transactions/999", headers=auth_headers)
    assert resp.status_code == 404


def test_create_transfer(client, auth_headers, account_id, other_account_id):
    resp = client.post(
        "/api/transactions/transfer",
        json={
            "from_account_id": account_id,
            "to_account_id": other_account_id,
            "date": "2026-01-01",
            "name": "Payment",
            "amount": 300.0,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    legs = resp.json()
    assert len(legs) == 2
    assert {leg["type"] for leg in legs} == {"transfer"}


def test_create_transfer_same_account_422(client, auth_headers, account_id):
    resp = client.post(
        "/api/transactions/transfer",
        json={
            "from_account_id": account_id,
            "to_account_id": account_id,
            "date": "2026-01-01",
            "name": "x",
            "amount": 10.0,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_create_transfer_unknown_account_404(client, auth_headers, account_id):
    resp = client.post(
        "/api/transactions/transfer",
        json={
            "from_account_id": account_id,
            "to_account_id": 999,
            "date": "2026-01-01",
            "name": "x",
            "amount": 10.0,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_uncategorized_count(client, auth_headers, account_id):
    client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "x", "splits": [{"amount": -1.0}]},
        headers=auth_headers,
    )
    resp = client.get("/api/transactions/uncategorized-count", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"count": 1}


def test_list_transactions_pagination_shape(client, auth_headers, account_id):
    for i in range(3):
        client.post(
            "/api/transactions",
            json={"account_id": account_id, "date": f"2026-01-0{i + 1}", "name": f"t{i}", "splits": [{"amount": -1.0}]},
            headers=auth_headers,
        )
    resp = client.get("/api/transactions?page=1&page_size=2", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["page_size"] == 2


def test_account_balance_reflects_transactions(client, auth_headers, account_id):
    client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "x", "splits": [{"amount": -100.0}]},
        headers=auth_headers,
    )
    resp = client.get(f"/api/accounts/{account_id}", headers=auth_headers)
    assert resp.json()["balance"] == 900.0

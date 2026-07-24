def test_requires_auth(client):
    resp = client.get("/api/accounts")
    assert resp.status_code == 401


def test_create_and_list_accounts(client, auth_headers):
    resp = client.post(
        "/api/accounts",
        json={"name": "Main checking", "type": "asset", "opening_balance": 100.0},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["balance"] == 100.0
    assert body["type"] == "asset"

    resp = client.get("/api/accounts", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_create_liability_account(client, auth_headers):
    resp = client.post(
        "/api/accounts",
        json={"name": "Shared credit card", "type": "liability", "opening_balance": -50},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["type"] == "liability"


def test_invalid_type_rejected(client, auth_headers):
    resp = client.post(
        "/api/accounts",
        json={"name": "x", "type": "checking", "opening_balance": 0},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_get_account(client, auth_headers):
    created = client.post(
        "/api/accounts", json={"name": "Main", "type": "asset"}, headers=auth_headers
    ).json()
    resp = client.get(f"/api/accounts/{created['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Main"


def test_get_missing_account_404(client, auth_headers):
    resp = client.get("/api/accounts/999", headers=auth_headers)
    assert resp.status_code == 404


def test_update_account(client, auth_headers):
    created = client.post(
        "/api/accounts", json={"name": "Main", "type": "asset"}, headers=auth_headers
    ).json()
    resp = client.patch(
        f"/api/accounts/{created['id']}",
        json={"name": "Main checking", "color": "#4f8a9c"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Main checking"
    assert body["color"] == "#4f8a9c"


def test_update_account_type_and_opening_balance(client, auth_headers):
    created = client.post(
        "/api/accounts", json={"name": "Main", "type": "asset"}, headers=auth_headers
    ).json()
    resp = client.patch(
        f"/api/accounts/{created['id']}",
        json={"type": "liability", "opening_balance": -25.5},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "liability"
    assert body["opening_balance"] == -25.5


def test_update_account_clears_account_number(client, auth_headers):
    created = client.post(
        "/api/accounts",
        json={"name": "Main", "type": "asset", "account_number": "1234"},
        headers=auth_headers,
    ).json()
    resp = client.patch(
        f"/api/accounts/{created['id']}",
        json={"account_number": None},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["account_number"] is None


def test_update_missing_account_404(client, auth_headers):
    resp = client.patch(
        "/api/accounts/999", json={"name": "x"}, headers=auth_headers
    )
    assert resp.status_code == 404

import pytest


@pytest.fixture()
def category_id(client, auth_headers):
    return client.post("/api/categories", json={"name": "personal"}, headers=auth_headers).json()["id"]


@pytest.fixture()
def account_id(client, auth_headers):
    return client.post(
        "/api/accounts", json={"name": "Main", "type": "asset", "opening_balance": 1000}, headers=auth_headers
    ).json()["id"]


def test_requires_auth(client):
    resp = client.get("/api/rules")
    assert resp.status_code == 401


def _rule_payload(category_id, value="github"):
    return {
        "match_type": "all",
        "conditions": [{"field": "name", "operator": "contains", "value": value}],
        "target_category_id": category_id,
    }


def test_create_and_list_rules(client, auth_headers, category_id):
    resp = client.post("/api/rules", json=_rule_payload(category_id), headers=auth_headers)
    assert resp.status_code == 201
    rule = resp.json()
    assert rule["priority"] == 0

    resp = client.get("/api/rules", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_create_rule_unknown_category_404(client, auth_headers):
    resp = client.post("/api/rules", json=_rule_payload(999), headers=auth_headers)
    assert resp.status_code == 404


def test_create_rule_no_conditions_422(client, auth_headers, category_id):
    payload = _rule_payload(category_id)
    payload["conditions"] = []
    resp = client.post("/api/rules", json=payload, headers=auth_headers)
    assert resp.status_code == 422


def test_create_rule_triggers_categorization(client, auth_headers, category_id, account_id):
    txn = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "GitHub Inc.", "splits": [{"amount": -21.0}]},
        headers=auth_headers,
    ).json()

    client.post("/api/rules", json=_rule_payload(category_id), headers=auth_headers)

    refreshed = client.get(f"/api/transactions/{txn['id']}", headers=auth_headers).json()
    assert refreshed["splits"][0]["suggested_category_id"] == category_id


def test_get_rule(client, auth_headers, category_id):
    created = client.post("/api/rules", json=_rule_payload(category_id), headers=auth_headers).json()
    resp = client.get(f"/api/rules/{created['id']}", headers=auth_headers)
    assert resp.status_code == 200


def test_get_missing_rule_404(client, auth_headers):
    resp = client.get("/api/rules/999", headers=auth_headers)
    assert resp.status_code == 404


def test_update_rule(client, auth_headers, category_id):
    created = client.post("/api/rules", json=_rule_payload(category_id), headers=auth_headers).json()
    resp = client.patch(
        f"/api/rules/{created['id']}",
        json={"conditions": [{"field": "name", "operator": "contains", "value": "spotify"}]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["conditions"][0]["value"] == "spotify"


def test_update_missing_rule_404(client, auth_headers):
    resp = client.patch("/api/rules/999", json={"match_type": "any"}, headers=auth_headers)
    assert resp.status_code == 404


def test_update_rule_bad_conditions_422(client, auth_headers, category_id):
    created = client.post("/api/rules", json=_rule_payload(category_id), headers=auth_headers).json()
    resp = client.patch(f"/api/rules/{created['id']}", json={"conditions": []}, headers=auth_headers)
    assert resp.status_code == 422


def test_delete_rule(client, auth_headers, category_id):
    created = client.post("/api/rules", json=_rule_payload(category_id), headers=auth_headers).json()
    resp = client.delete(f"/api/rules/{created['id']}", headers=auth_headers)
    assert resp.status_code == 204
    assert client.get(f"/api/rules/{created['id']}", headers=auth_headers).status_code == 404


def test_delete_missing_rule_404(client, auth_headers):
    resp = client.delete("/api/rules/999", headers=auth_headers)
    assert resp.status_code == 404


def test_reorder_rules(client, auth_headers, category_id):
    r1 = client.post("/api/rules", json=_rule_payload(category_id, "a"), headers=auth_headers).json()
    r2 = client.post("/api/rules", json=_rule_payload(category_id, "b"), headers=auth_headers).json()
    resp = client.post(
        "/api/rules/reorder", json={"ordered_ids": [r2["id"], r1["id"]]}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert [r["id"] for r in resp.json()] == [r2["id"], r1["id"]]


def test_reorder_rejects_bad_id_set(client, auth_headers, category_id):
    r1 = client.post("/api/rules", json=_rule_payload(category_id), headers=auth_headers).json()
    resp = client.post("/api/rules/reorder", json={"ordered_ids": [r1["id"], 999]}, headers=auth_headers)
    assert resp.status_code == 422


def test_suggestions_endpoint(client, auth_headers, category_id, account_id):
    for i in range(3):
        client.post(
            "/api/transactions",
            json={
                "account_id": account_id,
                "date": f"2026-01-0{i + 1}",
                "name": "GitHub Inc.",
                "splits": [{"category_id": category_id, "amount": -21.0}],
            },
            headers=auth_headers,
        )
    resp = client.get("/api/rules/suggestions", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["occurrence_count"] == 3


def test_recategorize_endpoint(client, auth_headers, category_id, account_id):
    txn = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "GitHub Inc.", "splits": [{"amount": -21.0}]},
        headers=auth_headers,
    ).json()
    client.post("/api/rules", json=_rule_payload(category_id), headers=auth_headers)
    resp = client.post("/api/rules/recategorize", json={"transaction_ids": [txn["id"]]}, headers=auth_headers)
    assert resp.status_code == 200
    # matches the rule again (idempotent re-suggest of the same category, not a "new" count)
    assert resp.json() == {"suggested_count": 1}


def test_accept_and_reject_suggestion_endpoints(client, auth_headers, category_id, account_id):
    txn = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "GitHub Inc.", "splits": [{"amount": -21.0}]},
        headers=auth_headers,
    ).json()
    client.post("/api/rules", json=_rule_payload(category_id), headers=auth_headers)
    refreshed = client.get(f"/api/transactions/{txn['id']}", headers=auth_headers).json()
    split_id = refreshed["splits"][0]["id"]

    resp = client.post(
        f"/api/transactions/{txn['id']}/splits/{split_id}/accept-suggestion", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["category_id"] == category_id


def test_reject_suggestion_endpoint(client, auth_headers, category_id, account_id):
    txn = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "GitHub Inc.", "splits": [{"amount": -21.0}]},
        headers=auth_headers,
    ).json()
    client.post("/api/rules", json=_rule_payload(category_id), headers=auth_headers)
    refreshed = client.get(f"/api/transactions/{txn['id']}", headers=auth_headers).json()
    split_id = refreshed["splits"][0]["id"]

    resp = client.post(
        f"/api/transactions/{txn['id']}/splits/{split_id}/reject-suggestion", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["category_id"] is None
    assert resp.json()["suggested_category_id"] is None


def test_accept_suggestion_missing_split_404(client, auth_headers, account_id):
    txn = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "x", "splits": [{"amount": -1.0}]},
        headers=auth_headers,
    ).json()
    resp = client.post(f"/api/transactions/{txn['id']}/splits/999/accept-suggestion", headers=auth_headers)
    assert resp.status_code == 404


def test_accept_suggestion_no_pending_422(client, auth_headers, account_id):
    txn = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "x", "splits": [{"amount": -1.0}]},
        headers=auth_headers,
    ).json()
    split_id = txn["splits"][0]["id"]
    resp = client.post(f"/api/transactions/{txn['id']}/splits/{split_id}/accept-suggestion", headers=auth_headers)
    assert resp.status_code == 422


def test_reject_suggestion_missing_split_404(client, auth_headers, account_id):
    txn = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "x", "splits": [{"amount": -1.0}]},
        headers=auth_headers,
    ).json()
    resp = client.post(f"/api/transactions/{txn['id']}/splits/999/reject-suggestion", headers=auth_headers)
    assert resp.status_code == 404


def test_reject_suggestion_no_pending_422(client, auth_headers, account_id):
    txn = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "x", "splits": [{"amount": -1.0}]},
        headers=auth_headers,
    ).json()
    split_id = txn["splits"][0]["id"]
    resp = client.post(f"/api/transactions/{txn['id']}/splits/{split_id}/reject-suggestion", headers=auth_headers)
    assert resp.status_code == 422

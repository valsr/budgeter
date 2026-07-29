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
def category_id(client, auth_headers):
    resp = client.post("/api/categories", json={"name": "shared"}, headers=auth_headers)
    return resp.json()["id"]


def _groups(client, auth_headers, **params):
    resp = client.get("/api/history", params=params, headers=auth_headers)
    assert resp.status_code == 200
    return resp.json()


def test_requires_auth(client):
    resp = client.get("/api/history")
    assert resp.status_code == 401


def test_create_account_appears_in_history(client, auth_headers, account_id):
    data = _groups(client, auth_headers)
    assert data["total"] == 1
    group = data["items"][0]
    assert group["entity_type"] == "account"
    assert group["operation"] == "create"
    assert "Main checking" in group["summary"]
    assert group["undone_at"] is None


def test_filter_by_entity_type(client, auth_headers, account_id, category_id):
    data = _groups(client, auth_headers, entity_type="category")
    assert data["total"] == 1
    assert data["items"][0]["entity_type"] == "category"


def test_pagination(client, auth_headers):
    for i in range(5):
        client.post("/api/accounts", json={"name": f"Acct {i}", "type": "asset"}, headers=auth_headers)

    page1 = _groups(client, auth_headers, page=1, page_size=2)
    assert page1["total"] == 5
    assert len(page1["items"]) == 2

    page3 = _groups(client, auth_headers, page=3, page_size=2)
    assert len(page3["items"]) == 1


def test_undo_single_create(client, auth_headers, account_id):
    group_id = _groups(client, auth_headers)["items"][0]["group_id"]

    resp = client.post("/api/history/undo", json={"group_ids": [group_id]}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["results"] == [{"group_id": group_id, "status": "undone", "reason": None}]

    resp = client.get(f"/api/accounts/{account_id}", headers=auth_headers)
    assert resp.status_code == 404


def test_undoing_a_create_self_logs_a_new_change_and_grays_out_the_original(client, auth_headers, account_id):
    group_id = _groups(client, auth_headers)["items"][0]["group_id"]
    client.post("/api/history/undo", json={"group_ids": [group_id]}, headers=auth_headers)

    data = _groups(client, auth_headers)
    assert data["total"] == 2
    by_group = {g["group_id"]: g for g in data["items"]}
    assert by_group[group_id]["undone_at"] is not None

    other = next(g for g in data["items"] if g["group_id"] != group_id)
    assert other["operation"] == "delete"


def test_undo_already_undone_is_skipped(client, auth_headers, account_id):
    group_id = _groups(client, auth_headers)["items"][0]["group_id"]
    client.post("/api/history/undo", json={"group_ids": [group_id]}, headers=auth_headers)

    resp = client.post("/api/history/undo", json={"group_ids": [group_id]}, headers=auth_headers)
    result = resp.json()["results"][0]
    assert result["status"] == "skipped"
    assert result["reason"] == "already undone"


def test_undo_create_blocked_by_dependents(client, auth_headers, account_id, category_id):
    client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "date": "2026-01-05",
            "name": "Costco",
            "splits": [{"category_id": category_id, "amount": -10}],
        },
        headers=auth_headers,
    )

    cat_group = next(
        g for g in _groups(client, auth_headers, entity_type="category")["items"] if g["operation"] == "create"
    )["group_id"]

    resp = client.post("/api/history/undo", json={"group_ids": [cat_group]}, headers=auth_headers)
    result = resp.json()["results"][0]
    assert result["status"] == "skipped"
    assert "transaction split" in result["reason"]

    # the category must still exist — the undo really was refused, not partially applied
    resp = client.get(f"/api/categories/{category_id}", headers=auth_headers)
    assert resp.status_code == 200


def test_undo_delete_blocked_by_pk_collision(client, auth_headers, db_session, account_id, category_id):
    import datetime as dt

    from app.models.transaction import Transaction, TransactionType

    resp = client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "date": "2026-01-05",
            "name": "Costco",
            "splits": [{"category_id": category_id, "amount": -10}],
        },
        headers=auth_headers,
    )
    txn_id = resp.json()["id"]

    client.delete(f"/api/transactions/{txn_id}", headers=auth_headers)
    delete_group = next(
        g
        for g in _groups(client, auth_headers, entity_type="transaction")["items"]
        if g["operation"] == "delete"
    )["group_id"]

    # Simulate the freed id being reassigned to an unrelated row before the
    # undo runs — db_session is the exact session the app's requests use
    # (see conftest.py's override_get_db), so this write is visible to the
    # undo call below.
    db_session.add(
        Transaction(id=txn_id, account_id=account_id, date=dt.date(2026, 1, 6), name="Unrelated", type=TransactionType.NORMAL)
    )
    db_session.commit()

    resp = client.post("/api/history/undo", json={"group_ids": [delete_group]}, headers=auth_headers)
    result = resp.json()["results"][0]
    assert result["status"] == "skipped"
    assert "now in use" in result["reason"]


def test_undo_batch_reverse_chronological_best_effort(client, auth_headers):
    r1 = client.post("/api/accounts", json={"name": "First", "type": "asset"}, headers=auth_headers)
    acc1 = r1.json()["id"]
    r2 = client.post("/api/accounts", json={"name": "Second", "type": "asset"}, headers=auth_headers)
    acc2 = r2.json()["id"]

    data = _groups(client, auth_headers)
    # newest first from the API already; find each account's create group
    group_by_name = {g["summary"]: g["group_id"] for g in data["items"]}
    g1 = group_by_name["Created account 'First'"]
    g2 = group_by_name["Created account 'Second'"]

    resp = client.post("/api/history/undo", json={"group_ids": [g1, g2]}, headers=auth_headers)
    results = {r["group_id"]: r["status"] for r in resp.json()["results"]}
    assert results == {g1: "undone", g2: "undone"}

    assert client.get(f"/api/accounts/{acc1}", headers=auth_headers).status_code == 404
    assert client.get(f"/api/accounts/{acc2}", headers=auth_headers).status_code == 404


def test_is_stale_flags_update_superseded_by_a_later_change(client, auth_headers, account_id):
    client.patch(f"/api/accounts/{account_id}", json={"name": "Rename 1"}, headers=auth_headers)
    client.patch(f"/api/accounts/{account_id}", json={"name": "Rename 2"}, headers=auth_headers)

    data = _groups(client, auth_headers, entity_type="account")
    updates = [g for g in data["items"] if g["operation"] == "update"]
    # oldest update (Checking -> Rename 1) is now stale; newest is not
    stale_by_summary = {g["summary"]: g["is_stale"] for g in updates}
    assert stale_by_summary["Renamed account 'Main checking' to 'Rename 1'"] is True
    assert stale_by_summary["Renamed account 'Rename 1' to 'Rename 2'"] is False


def test_undo_stale_update_is_allowed(client, auth_headers, account_id):
    client.patch(f"/api/accounts/{account_id}", json={"name": "Rename 1"}, headers=auth_headers)
    client.patch(f"/api/accounts/{account_id}", json={"name": "Rename 2"}, headers=auth_headers)

    data = _groups(client, auth_headers, entity_type="account")
    stale_group = next(
        g
        for g in data["items"]
        if g["summary"] == "Renamed account 'Main checking' to 'Rename 1'"
    )["group_id"]

    resp = client.post("/api/history/undo", json={"group_ids": [stale_group]}, headers=auth_headers)
    assert resp.json()["results"][0]["status"] == "undone"

    resp = client.get(f"/api/accounts/{account_id}", headers=auth_headers)
    assert resp.json()["name"] == "Main checking"


def test_unknown_group_id_is_skipped(client, auth_headers):
    resp = client.post("/api/history/undo", json={"group_ids": ["not-a-real-group"]}, headers=auth_headers)
    result = resp.json()["results"][0]
    assert result["status"] == "skipped"
    assert result["reason"] == "change group not found"

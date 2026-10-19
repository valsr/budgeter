import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import shared_books
from app.main import app
from tests.helpers import make_account, tables

B = "/api/shared-budgets"


@pytest.fixture()
def trio(make_client):
    return make_client("alice"), make_client("bob"), make_client("carol")


def _create(client, name="Home", member_ids=()):
    resp = client.post(B, json={"name": name, "member_ids": list(member_ids)})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _category(client, name):
    resp = client.post("/api/categories", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _spend(client, account_id, category_id, amount, name="Costco", date="2026-01-05"):
    resp = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": date, "name": name, "splits": [{"category_id": category_id, "amount": amount}]},
    )
    assert resp.status_code == 201, resp.text


def test_create_list_rename_delete(trio):
    alice, bob, carol = trio
    budget = _create(alice, member_ids=[bob.user_id])
    assert budget["name"] == "Home"
    assert {m["user_id"] for m in budget["members"]} == {alice.user_id, bob.user_id}
    assert all(set(m) == {"user_id", "username", "is_disabled"} for m in budget["members"])

    assert [b["id"] for b in bob.get(B).json()] == [budget["id"]]
    assert carol.get(B).json() == []

    resp = bob.patch(f"{B}/{budget['id']}", json={"name": "Flat"})
    assert resp.status_code == 200 and resp.json()["name"] == "Flat"
    assert alice.get(f"{B}/{budget['id']}").json()["name"] == "Flat"

    assert alice.delete(f"{B}/{budget['id']}").status_code == 204
    assert alice.get(B).json() == []
    assert not shared_books.shared_path(budget["id"]).exists()


def test_non_member_gets_404_everywhere(trio):
    alice, _bob, carol = trio
    bid = _create(alice)["id"]
    cat = alice.post(f"{B}/{bid}/categories", json={"name": "Food"}).json()["id"]
    p = f"{B}/{bid}"
    calls = [
        ("GET", p, None),
        ("PATCH", p, {"name": "x"}),
        ("PUT", f"{p}/members", {"user_ids": [carol.user_id]}),
        ("GET", f"{p}/categories", None),
        ("POST", f"{p}/categories", {"name": "x"}),
        ("PATCH", f"{p}/categories/{cat}", {"name": "x"}),
        ("DELETE", f"{p}/categories/{cat}", None),
        ("GET", f"{p}/amounts?year=2026", None),
        ("PUT", f"{p}/amounts", {"year": 2026, "lines": []}),
        ("GET", f"{p}/links", None),
        ("PUT", f"{p}/links", {"links": []}),
        ("GET", f"{p}/report?year=2026&through_month=1", None),
        ("DELETE", p, None),
    ]
    for method, url, body in calls:
        resp = carol.request(method, url, json=body)
        assert resp.status_code == 404, (method, url, resp.status_code)
    # and nothing changed
    assert alice.get(p).json()["name"] == "Home"
    assert len(alice.get(f"{p}/categories").json()) == 1


def test_members_cannot_become_empty(trio):
    alice, _bob, _carol = trio
    bid = _create(alice)["id"]
    assert alice.put(f"{B}/{bid}/members", json={"user_ids": []}).status_code == 422
    assert [m["user_id"] for m in alice.get(f"{B}/{bid}").json()["members"]] == [alice.user_id]


def test_leaving_removes_access_and_tally(trio):
    alice, bob, _carol = trio
    bid = _create(alice, member_ids=[bob.user_id])["id"]
    cat = alice.post(f"{B}/{bid}/categories", json={"name": "Food"}).json()["id"]
    for client in (alice, bob):
        books_cat = _category(client, "groceries")
        assert client.put(f"{B}/{bid}/links", json={"links": [{"category_id": books_cat, "shared_category_id": cat}]}).status_code == 200
        _spend(client, make_account(client, "Checking"), books_cat, -10.0)

    report = alice.get(f"{B}/{bid}/report?year=2026&through_month=1").json()
    assert {m["user_id"] for m in report[0]["members"]} == {alice.user_id, bob.user_id}

    resp = bob.put(f"{B}/{bid}/members", json={"user_ids": [alice.user_id]})
    assert resp.status_code == 200, resp.text
    assert bob.get(f"{B}/{bid}").status_code == 404
    assert bob.get(B).json() == []
    report = alice.get(f"{B}/{bid}/report?year=2026&through_month=1").json()
    assert [m["user_id"] for m in report[0]["members"]] == [alice.user_id]
    assert report[0]["monthly"]["1"]["actual"] == 10.0


def test_end_to_end_report(trio):
    alice, bob, _carol = trio
    bid = _create(alice, member_ids=[bob.user_id])["id"]
    p = f"{B}/{bid}"
    cat = alice.post(f"{p}/categories", json={"name": "Groceries"}).json()["id"]
    resp = alice.put(f"{p}/amounts", json={"year": 2026, "lines": [{"shared_category_id": cat, "month": 1, "amount": 500}]})
    assert resp.status_code == 200
    assert resp.json() == [{"shared_category_id": cat, "month": 1, "amount": 500.0}]
    assert bob.get(f"{p}/amounts?year=2026").json() == resp.json()

    spend = {alice: 120.0, bob: 80.5}
    for client, amount in spend.items():
        books_cat = _category(client, "groceries")
        resp = client.put(f"{p}/links", json={"links": [{"category_id": books_cat, "shared_category_id": cat}]})
        assert resp.status_code == 200, resp.text
        assert resp.json() == [{"category_id": books_cat, "shared_category_id": cat}]
        _spend(client, make_account(client, "Checking"), books_cat, -amount)

    rows = bob.get(f"{p}/report?year=2026&through_month=1").json()
    assert len(rows) == 1
    row = rows[0]
    assert row["row_key"] == f"shared:{cat}"
    assert row["category_id"] == cat and row["account_id"] is None
    assert row["monthly"]["1"] == {"budgeted": 500.0, "actual": 200.5}
    split = {m["user_id"]: m for m in row["members"]}
    assert split[alice.user_id]["ytd_actual"] == 120.0
    assert split[bob.user_id]["ytd_actual"] == 80.5
    assert split[alice.user_id]["username"] == "alice"
    assert split[bob.user_id]["monthly"]["1"] == 80.5

    assert alice.get(f"{p}/report?year=2026&through_month=13").status_code == 422


def test_category_crud(trio):
    alice, _bob, _carol = trio
    p = f"{B}/{_create(alice)['id']}"
    parent = alice.post(f"{p}/categories", json={"name": "Home"}).json()
    child = alice.post(f"{p}/categories", json={"name": "Rent", "parent_id": parent["id"], "is_income": False}).json()
    assert child["parent_id"] == parent["id"] and child["archived"] is False
    resp = alice.patch(f"{p}/categories/{child['id']}", json={"archived": True, "parent_id": None})
    assert resp.status_code == 200 and resp.json()["archived"] is True and resp.json()["parent_id"] is None
    assert alice.patch(f"{p}/categories/{parent['id']}", json={"parent_id": parent["id"]}).status_code == 422
    assert len(alice.get(f"{p}/categories").json()) == 2
    assert alice.delete(f"{p}/categories/{child['id']}").status_code == 204


def test_links_are_per_member(trio):
    alice, bob, _carol = trio
    bid = _create(alice, member_ids=[bob.user_id])["id"]
    p = f"{B}/{bid}"
    cat = alice.post(f"{p}/categories", json={"name": "Food"}).json()["id"]
    a_cat = _category(alice, "a-groceries")
    assert alice.put(f"{p}/links", json={"links": [{"category_id": a_cat, "shared_category_id": cat}]}).status_code == 200
    assert alice.get(f"{p}/links").json() == [{"category_id": a_cat, "shared_category_id": cat}]
    assert bob.get(f"{p}/links").json() == []
    # a category that isn't in the caller's own books is rejected
    assert bob.put(f"{p}/links", json={"links": [{"category_id": 999, "shared_category_id": cat}]}).status_code == 422


def test_directory_exposes_only_id_and_username(trio):
    alice, bob, carol = trio
    resp = alice.patch(f"/api/admin/users/{carol.user_id}", json={"is_disabled": True})
    assert resp.status_code == 200, resp.text
    resp = bob.get("/api/users/directory")
    assert resp.status_code == 200
    users = resp.json()
    assert {u["username"] for u in users} == {"alice", "bob"}
    assert all(set(u) == {"id", "username"} for u in users)
    assert TestClient(app).get("/api/users/directory").status_code == 401


def test_startup_rebuilds_tallies(trio):
    alice, _bob, _carol = trio
    bid = _create(alice)["id"]
    p = f"{B}/{bid}"
    cat = alice.post(f"{p}/categories", json={"name": "Food"}).json()["id"]
    books_cat = _category(alice, "groceries")
    alice.put(f"{p}/links", json={"links": [{"category_id": books_cat, "shared_category_id": cat}]})
    _spend(alice, make_account(alice, "Checking"), books_cat, -42.0)
    before = alice.get(f"{p}/report?year=2026&through_month=1").json()
    assert before[0]["monthly"]["1"]["actual"] == 42.0

    shared_books.dispose(bid)
    conn = sqlite3.connect(shared_books.shared_path(bid))
    conn.execute("DELETE FROM member_tallies")
    conn.commit()
    conn.close()
    assert alice.get(f"{p}/report?year=2026&through_month=1").json()[0]["monthly"]["1"]["actual"] == 0.0

    with TestClient(app) as fresh:  # entering the context runs the lifespan
        fresh.cookies.update(alice.cookies)
        assert fresh.get(f"{p}/report?year=2026&through_month=1").json() == before


def test_startup_survives_one_corrupt_shared_file(trio):
    alice, _bob, _carol = trio
    first = _create(alice, "First")["id"]
    second = _create(alice, "Second")["id"]
    p = f"{B}/{second}"
    cat = alice.post(f"{p}/categories", json={"name": "Food"}).json()["id"]
    books_cat = _category(alice, "groceries")
    alice.put(f"{p}/links", json={"links": [{"category_id": books_cat, "shared_category_id": cat}]})
    _spend(alice, make_account(alice, "Checking"), books_cat, -42.0)

    shared_books.dispose(first)
    shared_books.dispose(second)
    shared_books.shared_path(first).write_bytes(b"this is not a sqlite database" * 100)
    # An empty, never-migrated file: only startup's upgrade gives it a schema.
    shared_books.shared_path(second).unlink()
    sqlite3.connect(shared_books.shared_path(second)).close()

    with TestClient(app) as fresh:
        fresh.cookies.update(alice.cookies)
        assert "shared_categories" in tables(shared_books.shared_path(second))
        assert fresh.get(f"{p}/report?year=2026&through_month=1").status_code == 200

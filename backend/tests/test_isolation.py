import sqlite3

from app import books


def make_account(client, name):
    resp = client.post("/api/accounts", json={"name": name, "type": "asset"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_users_cannot_see_or_fetch_each_others_data(make_client):
    alice, bob = make_client("alice"), make_client("bob")

    account_id = make_account(alice, "Alice checking")
    resp = alice.post("/api/categories", json={"name": "alice-groceries"})
    assert resp.status_code == 201, resp.text

    assert bob.get("/api/accounts").json() == []
    assert bob.get("/api/categories").json() == []
    assert bob.get("/api/transactions").json()["total"] == 0
    assert bob.get("/api/budgets").json() == []
    assert bob.get("/api/history").json()["total"] == 0

    assert bob.patch(f"/api/accounts/{account_id}", json={"name": "hijacked"}).status_code == 404
    assert bob.get(f"/api/transactions?account_id={account_id}").json()["total"] == 0
    assert [a["name"] for a in alice.get("/api/accounts").json()] == ["Alice checking"]

    # Ids are per-books: bob's first account reuses alice's id without touching hers.
    assert make_account(bob, "Bob savings") == account_id
    assert [a["name"] for a in alice.get("/api/accounts").json()] == ["Alice checking"]
    assert [a["name"] for a in bob.get("/api/accounts").json()] == ["Bob savings"]


def test_each_user_has_their_own_settings(make_client):
    alice, bob = make_client("alice"), make_client("bob")
    assert alice.patch("/api/settings/retention", json={"retention_days": 7}).status_code == 200
    assert alice.get("/api/settings/retention").json() == {"retention_days": 7}
    assert bob.get("/api/settings/retention").json() == {"retention_days": 100}


def test_registering_creates_the_users_books_file(make_client, files):
    alice = make_client("alice")
    assert books.books_path(alice.user_id).exists()
    assert sorted(p.name for p in (files / "books").iterdir()) == [f"{alice.user_id}.db"]


def test_first_registration_takes_over_the_legacy_database(make_client, files):
    from tests.test_books import make_legacy

    make_legacy(files)
    alice = make_client("alice")
    assert [a["name"] for a in alice.get("/api/accounts").json()] == ["Main"]
    # The carried-over key keeps an already-configured MCP adapter working.
    anonymous = make_client()
    resp = anonymous.get("/api/accounts", headers={"Authorization": "Bearer legacy-key"})
    assert [a["name"] for a in resp.json()] == ["Main"]

    bob = make_client("bob")
    assert bob.get("/api/accounts").json() == []


def test_a_user_whose_books_file_vanished_gets_fresh_empty_books(make_client):
    alice = make_client("alice")
    make_account(alice, "Checking")
    books.delete_books(alice.user_id)  # e.g. removed by hand outside the app
    resp = alice.get("/api/accounts")
    assert resp.status_code == 200
    assert resp.json() == []


QIF = """!Type:Bank
D01/05/2026
T-12.50
PCoffee Shop
^
"""


def test_background_categorization_runs_against_the_importers_books(make_client):
    alice, bob = make_client("alice"), make_client("bob")
    make_account(bob, "Bob checking")  # same id as alice's account, different books
    account_id = make_account(alice, "Alice checking")
    category_id = alice.post("/api/categories", json={"name": "coffee"}).json()["id"]
    resp = alice.post(
        "/api/rules",
        json={
            "match_type": "all",
            "target_category_id": category_id,
            "conditions": [{"field": "name", "operator": "contains", "value": "coffee"}],
        },
    )
    assert resp.status_code == 201, resp.text

    resp = alice.post(
        "/api/import", data={"account_id": account_id}, files={"file": ("a.qif", QIF, "text/plain")}
    )
    assert resp.status_code == 201, resp.text

    # TestClient runs background tasks before returning, so the rule has
    # already been applied -- in alice's books, and only there.
    conn = sqlite3.connect(books.books_path(alice.user_id))
    suggested = conn.execute("SELECT suggested_category_id, category_id FROM splits").fetchall()
    conn.close()
    assert suggested and all(category_id in row for row in suggested)
    assert bob.get("/api/transactions").json()["total"] == 0

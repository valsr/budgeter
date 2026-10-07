import sqlite3

from app import books
from app.services import backup as backup_svc


def make_account(client, name):
    resp = client.post("/api/accounts", json={"name": name, "type": "asset"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def account_names(client):
    return [a["name"] for a in client.get("/api/accounts").json()]


def restore(client, data: bytes):
    return client.post("/api/backup/restore", files={"file": ("backup.db", data, "application/octet-stream")})


def test_requires_auth(make_client):
    anonymous = make_client()
    assert anonymous.get("/api/backup").status_code == 401
    assert restore(anonymous, b"x").status_code == 401


def test_download_backup_returns_my_books_as_a_sqlite_file(make_client, tmp_path):
    alice = make_client("alice")
    make_account(alice, "Main checking")

    resp = alice.get("/api/backup")
    assert resp.status_code == 200
    assert resp.content.startswith(backup_svc.SQLITE_MAGIC)
    assert "attachment" in resp.headers["content-disposition"]

    downloaded = tmp_path / "downloaded.db"
    downloaded.write_bytes(resp.content)
    conn = sqlite3.connect(str(downloaded))
    rows = conn.execute("SELECT name FROM accounts").fetchall()
    conn.close()
    assert rows == [("Main checking",)]


def test_download_then_restore_round_trips_my_books(make_client):
    alice = make_client("alice")
    make_account(alice, "Before")
    snapshot = alice.get("/api/backup").content

    make_account(alice, "After")
    assert account_names(alice) == ["Before", "After"]

    assert restore(alice, snapshot).status_code == 204
    assert account_names(alice) == ["Before"]


def test_restore_does_not_touch_another_users_books(make_client):
    alice, bob = make_client("alice"), make_client("bob")
    make_account(bob, "Bob savings")
    empty = alice.get("/api/backup").content
    make_account(alice, "Alice checking")

    assert restore(alice, empty).status_code == 204
    assert account_names(alice) == []
    assert account_names(bob) == ["Bob savings"]
    # ...and bob can't be handed alice's books by restoring his own backup.
    assert books.books_path(alice.user_id) != books.books_path(bob.user_id)


def test_restore_rejects_invalid_file(make_client):
    alice = make_client("alice")
    make_account(alice, "Keep me")
    resp = restore(alice, b"definitely not sqlite")
    assert resp.status_code == 422
    assert account_names(alice) == ["Keep me"]

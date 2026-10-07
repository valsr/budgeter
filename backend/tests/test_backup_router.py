import sqlite3

from app import books
from app.services import backup as backup_svc
from tests.helpers import account_names, make_account


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


def test_restore_upgrades_an_older_books_file(make_client, tmp_path):
    from tests.test_books import PRE_ACCOUNTS_HEAD

    old = tmp_path / "old.db"
    books.upgrade(old, PRE_ACCOUNTS_HEAD)
    conn = sqlite3.connect(old)
    conn.execute(
        "INSERT INTO accounts (name, type, opening_balance, created_at) VALUES ('Old', 'ASSET', 0, '2026-01-01')"
    )
    conn.commit()
    conn.close()

    alice = make_client("alice")
    assert restore(alice, old.read_bytes()).status_code == 204
    assert account_names(alice) == ["Old"]
    conn = sqlite3.connect(books.books_path(alice.user_id))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "api_key" not in tables  # migrated to head after the swap


def _wrong_file(kind: str, files, tmp_path) -> bytes:
    if kind == "not_sqlite":
        return b"definitely not sqlite"
    if kind == "server_db":
        return (files / "server.db").read_bytes()
    path = tmp_path / f"{kind}.db"
    books.upgrade(path)
    conn = sqlite3.connect(path)
    if kind == "unknown_revision":
        conn.execute("UPDATE alembic_version SET version_num = 'ffffffffffff'")
    elif kind == "no_alembic_version":
        conn.execute("DROP TABLE alembic_version")
    conn.commit()
    conn.close()
    return path.read_bytes()


import pytest  # noqa: E402


@pytest.mark.parametrize("kind", ["not_sqlite", "server_db", "unknown_revision", "no_alembic_version"])
def test_restore_rejects_the_wrong_file_and_keeps_current_books(make_client, files, tmp_path, kind):
    alice = make_client("alice")
    make_account(alice, "Keep me")
    before = books.books_path(alice.user_id).read_bytes()

    resp = restore(alice, _wrong_file(kind, files, tmp_path))

    assert resp.status_code == 422, kind
    assert books.books_path(alice.user_id).read_bytes() == before
    assert account_names(alice) == ["Keep me"]

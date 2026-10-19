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


def test_single_user_restore_recomputes_tally(make_client):
    from app import shared_books
    from app.shared_models import MemberTally

    alice, bob = make_client("alice"), make_client("bob")
    bid = alice.post("/api/shared-budgets", json={"name": "Home", "member_ids": [bob.user_id]}).json()["id"]
    sid = alice.post(f"/api/shared-budgets/{bid}/categories", json={"name": "Groceries"}).json()["id"]
    own = alice.post("/api/categories", json={"name": "Food"}).json()["id"]
    account = make_account(alice, "Card")

    assert alice.put(
        f"/api/shared-budgets/{bid}/links", json={"links": [{"category_id": own, "shared_category_id": sid}]}
    ).status_code == 200
    # Back up with the link in place, then add a transaction the backup doesn't have.
    older = alice.get("/api/backup").content
    resp = alice.post(
        "/api/transactions",
        json={"account_id": account, "date": "2026-01-10", "name": "Shop", "splits": [{"category_id": own, "amount": -25}]},
    )
    assert resp.status_code == 201, resp.text

    def tally():
        with shared_books.session_for(bid) as s:
            return [(t.user_id, t.shared_category_id, t.year, t.month) for t in s.query(MemberTally)]

    assert tally() == [(alice.user_id, sid, 2026, 1)]

    assert restore(alice, older).status_code == 204
    assert tally() == []


def test_restore_succeeds_even_if_the_tally_update_fails(make_client, monkeypatch):
    from app.services import shared_tally

    alice = make_client("alice")
    make_account(alice, "Before")
    snapshot = alice.get("/api/backup").content
    make_account(alice, "After")

    def boom(user_id):
        raise RuntimeError("tally broke")

    monkeypatch.setattr(shared_tally, "recompute_member", boom)
    assert restore(alice, snapshot).status_code == 204
    assert account_names(alice) == ["Before"]

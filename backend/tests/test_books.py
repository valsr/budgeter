import sqlite3

import pytest
from sqlalchemy import select

from app import books, server_db
from app.models import Account, AccountType
from app.security import hash_token
from app.server_models import User
from app.services import users

# The books head just before the api_key table was dropped, and the tree's root.
PRE_ACCOUNTS_HEAD = "1ed80c4a4e60"
ROOT_REVISION = "5928280a1455"


def tables(path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def make_legacy(files, revision=PRE_ACCOUNTS_HEAD, api_key="legacy-key"):
    path = files / "budgeter.db"
    books.upgrade(path, revision)
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO accounts (name, type, opening_balance, created_at) VALUES ('Main', 'ASSET', 0, '2026-01-01')"
    )
    if api_key is not None:
        conn.execute("INSERT INTO api_key (key, updated_at) VALUES (?, '2026-01-01')", (api_key,))
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def sdb(files):
    with server_db.SessionLocal() as db:
        yield db


def new_user(sdb, name):
    user = User(username=name, password_hash="!")
    sdb.add(user)
    sdb.commit()
    return user


def account_names(user_id):
    with books.session_for(user_id) as db:
        return [a.name for a in db.execute(select(Account)).scalars()]


def test_session_for_creates_and_migrates_a_missing_file(files):
    assert not books.books_path(7).exists()
    with books.session_for(7) as db:
        assert db.execute(select(Account)).scalars().all() == []
    assert books.books_path(7) == files / "books" / "7.db"
    found = tables(books.books_path(7))
    assert {"accounts", "categories", "transactions", "splits", "rules", "app_settings", "alembic_version"} <= found
    assert "api_key" not in found
    assert "users" not in found


def test_each_user_gets_a_separate_file(files):
    with books.session_for(1) as db:
        db.add(Account(name="Mine", type=AccountType.ASSET))
        db.commit()
    assert account_names(1) == ["Mine"]
    assert account_names(2) == []
    assert books.books_path(1) != books.books_path(2)


def test_upgrade_is_idempotent(files):
    books.create_books(3)
    books.upgrade(books.books_path(3))
    books.upgrade_all([3, 99])  # a user with no file yet is skipped, not created
    assert not books.books_path(99).exists()


def test_upgrade_all_is_a_no_op_in_memory(server_session):
    books.upgrade_all([1])  # would raise if it tried to run Alembic here
    books.create_books(1)
    assert account_names(1) == []


def test_delete_books_removes_the_file_and_tolerates_a_missing_one(files):
    books.create_books(4)
    account_names(4)  # leave an engine cached, as a live server would
    books.delete_books(4)
    assert not books.books_path(4).exists()
    books.delete_books(4)
    books.delete_books(12345)


def test_first_user_claims_a_copy_of_the_legacy_database(files, sdb):
    legacy = make_legacy(files)
    before = legacy.read_bytes()
    first = new_user(sdb, "first")

    assert books.claim_legacy_books(sdb, first) is True

    assert account_names(first.id) == ["Main"]
    assert first.api_key_hash == hash_token("legacy-key")
    assert users.get_settings(sdb).legacy_books_claimed is True
    assert "api_key" not in tables(books.books_path(first.id))
    assert legacy.read_bytes() == before  # never modified
    assert sorted(p.name for p in files.iterdir()) == ["books", "budgeter.db", "server.db"]


def test_second_user_does_not_claim(files, sdb):
    make_legacy(files)
    first, second = new_user(sdb, "first"), new_user(sdb, "second")
    # Even with the flag still unset, only a server's very first user qualifies.
    assert books.claim_legacy_books(sdb, second) is False
    sdb.delete(second)
    sdb.commit()
    assert books.claim_legacy_books(sdb, first) is True
    third = new_user(sdb, "third")
    assert books.claim_legacy_books(sdb, third) is False
    assert account_names(third.id) == []


def test_legacy_books_are_not_handed_out_again_after_the_claimant_is_deleted(files, sdb):
    make_legacy(files)
    first = new_user(sdb, "first")
    assert books.claim_legacy_books(sdb, first) is True
    sdb.delete(first)
    sdb.commit()
    again = new_user(sdb, "again")
    assert books.claim_legacy_books(sdb, again) is False


def test_claim_without_a_legacy_file_is_a_no_op(files, sdb):
    first = new_user(sdb, "first")
    assert books.claim_legacy_books(sdb, first) is False
    assert users.get_settings(sdb).legacy_books_claimed is False
    assert not books.books_path(first.id).exists()


def test_claim_ignores_a_file_that_is_not_a_budgeter_database(files, sdb):
    (files / "budgeter.db").write_bytes(b"")
    first = new_user(sdb, "first")
    assert books.claim_legacy_books(sdb, first) is False
    conn = sqlite3.connect(files / "budgeter.db")
    conn.execute("CREATE TABLE unrelated (id INTEGER)")
    conn.commit()
    conn.close()
    assert books.claim_legacy_books(sdb, first) is False


def test_legacy_database_without_a_stored_key_leaves_the_user_keyless(files, sdb):
    make_legacy(files, api_key=None)
    first = new_user(sdb, "first")
    assert books.claim_legacy_books(sdb, first) is True
    assert first.api_key_hash is None


def test_legacy_database_at_an_old_revision_is_upgraded_on_claim(files, sdb):
    # The root revision predates the api_key table entirely.
    make_legacy(files, revision=ROOT_REVISION, api_key=None)
    first = new_user(sdb, "first")
    assert books.claim_legacy_books(sdb, first) is True
    assert account_names(first.id) == ["Main"]
    assert "app_settings" in tables(books.books_path(first.id))

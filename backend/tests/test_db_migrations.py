import sqlite3

from app import books, server_db
from app.config import settings


def _tables(path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def test_books_upgrade_creates_schema_on_a_fresh_db_file(tmp_path):
    """Regression test: a fresh/missing books file (new user, new checkout,
    or a migration added since the file was last touched) must self-heal to
    the current schema rather than 500ing on "no such table" the first time
    a route queries it.
    """
    db_path = tmp_path / "books" / "1.db"

    books.upgrade(db_path)

    assert db_path.exists()
    assert {
        "accounts",
        "categories",
        "transactions",
        "splits",
        "rules",
        "account_changes",
        "category_changes",
        "transaction_changes",
        "app_settings",
    } <= _tables(db_path)
    # Users and their keys live in the server database, never in books.
    assert not {"api_key", "users", "sessions"} & _tables(db_path)


def test_books_upgrade_is_idempotent(tmp_path):
    db_path = tmp_path / "fresh.db"

    books.upgrade(db_path)
    books.upgrade(db_path)  # must not error on an already-current schema

    assert db_path.exists()


def test_the_two_trees_stay_out_of_each_others_files(files):
    books.create_books(1)
    assert "accounts" not in _tables(files / "server.db")
    assert "users" not in _tables(files / "books" / "1.db")


def test_upgrades_skip_the_in_memory_test_sentinel(monkeypatch):
    # "sqlite://" (no file) is what tests/conftest.py sets as the default
    # BUDGETER_DATABASE_URL — tables are created directly via create_all
    # there, so these must no-op rather than trying to run a real Alembic
    # migration against an anonymous in-memory DB.
    monkeypatch.setattr(settings, "database_url", "sqlite://")
    monkeypatch.setattr(settings, "data_dir", None)
    server_db.upgrade_to_head()
    books.upgrade_all([1, 2])  # would raise if it attempted to run migrations here

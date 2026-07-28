import sqlite3

from app.config import settings
from app.db import upgrade_to_head


def test_upgrade_to_head_creates_schema_on_a_fresh_db_file(tmp_path, monkeypatch):
    """Regression test: a fresh/missing DB file (new checkout, or a
    migration added since the file was last touched) must self-heal to the
    current schema on startup rather than 500ing on "no such table" the
    first time a route queries it.
    """
    db_path = tmp_path / "fresh.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")

    upgrade_to_head()

    assert db_path.exists()
    conn = sqlite3.connect(db_path)
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert {"accounts", "categories", "transactions", "splits", "rules", "api_key"} <= tables


def test_upgrade_to_head_is_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "fresh.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")

    upgrade_to_head()
    upgrade_to_head()  # must not error on an already-current schema

    assert db_path.exists()


def test_upgrade_to_head_skips_the_in_memory_test_sentinel(monkeypatch):
    # "sqlite://" (no file) is what tests/conftest.py sets as the default
    # BUDGETER_DATABASE_URL — the test suite creates tables itself via
    # Base.metadata.create_all, so this must no-op rather than trying to run
    # a real Alembic migration against an anonymous in-memory DB.
    monkeypatch.setattr(settings, "database_url", "sqlite://")
    upgrade_to_head()  # would raise if it attempted to run migrations here


from app import books, server_db, shared_books
from app.config import settings
from tests.helpers import tables


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
        "shared_category_links",
    } <= tables(db_path)
    # Users and their keys live in the server database, never in books.
    assert not {"api_key", "users", "sessions"} & tables(db_path)


def test_server_upgrade_creates_shared_registry(files):
    assert {"shared_budgets", "shared_budget_members"} <= tables(files / "server.db")
    books.create_books(1)
    assert not {"shared_budgets", "shared_budget_members"} & tables(files / "books" / "1.db")


def test_books_upgrade_is_idempotent(tmp_path):
    db_path = tmp_path / "fresh.db"

    books.upgrade(db_path)
    books.upgrade(db_path)  # must not error on an already-current schema

    assert db_path.exists()


def test_the_two_trees_stay_out_of_each_others_files(files):
    books.create_books(1)
    assert "accounts" not in tables(files / "server.db")
    assert "users" not in tables(files / "books" / "1.db")
    shared_books.create(1)
    assert not {"users", "accounts"} & tables(files / "shared" / "1.db")
    assert "member_tallies" not in tables(files / "books" / "1.db")
    assert "member_tallies" not in tables(files / "server.db")


def test_upgrades_skip_the_in_memory_test_sentinel(monkeypatch):
    # "sqlite://" (no file) is what tests/conftest.py sets as the default
    # BUDGETER_DATABASE_URL — tables are created directly via create_all
    # there, so these must no-op rather than trying to run a real Alembic
    # migration against an anonymous in-memory DB.
    monkeypatch.setattr(settings, "database_url", "sqlite://")
    monkeypatch.setattr(settings, "data_dir", None)
    server_db.upgrade_to_head()
    shared_books.upgrade_all([1])
    books.upgrade_all([1, 2])  # would raise if it attempted to run migrations here


def _schema_drift(path, metadata) -> list:
    """What autogenerate would emit for a file at head: anything here means a model change shipped
    without its migration."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{path}")
    try:
        with engine.connect() as conn:
            return compare_metadata(MigrationContext.configure(conn), metadata)
    finally:
        engine.dispose()


def test_books_migrations_match_the_models(tmp_path):
    from app import models  # noqa: F401
    from app.db import Base

    books.upgrade(tmp_path / "books.db")
    assert _schema_drift(tmp_path / "books.db", Base.metadata) == []


def test_server_migrations_match_the_models(tmp_path):
    from app import server_models  # noqa: F401
    from app.server_db import ServerBase, upgrade_path

    upgrade_path(tmp_path / "server.db")
    assert _schema_drift(tmp_path / "server.db", ServerBase.metadata) == []


def test_shared_migrations_match_the_models(tmp_path):
    from app import shared_models  # noqa: F401
    from app.shared_db import SharedBase

    shared_books.upgrade(tmp_path / "shared.db")
    assert _schema_drift(tmp_path / "shared.db", SharedBase.metadata) == []


def test_widening_rule_condition_operator_keeps_conditions(tmp_path):
    import sqlite3

    path = tmp_path / "books.db"
    books.upgrade(path, revision="c7d9d692529a")
    conn = sqlite3.connect(path)
    with conn:
        conn.execute("INSERT INTO categories (id, name, sort_order, is_income) VALUES (1, 'food', 0, 0)")
        conn.execute("INSERT INTO rules (id, match_type, priority, target_category_id) VALUES (1, 'ALL', 0, 1)")
        conn.execute(
            "INSERT INTO rule_conditions (id, rule_id, field, operator, value) "
            "VALUES (1, 1, 'AMOUNT', 'IS_WITHDRAWAL', '')"
        )
    conn.close()

    books.upgrade(path)

    conn = sqlite3.connect(path)
    try:
        rows = conn.execute("SELECT id, rule_id, field, operator, value FROM rule_conditions").fetchall()
        ddl = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'rule_conditions'").fetchone()[0]
    finally:
        conn.close()
    assert rows == [(1, 1, "AMOUNT", "IS_WITHDRAWAL", "")]
    assert "VARCHAR(13)" in ddl

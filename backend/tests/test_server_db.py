import sqlite3

import pytest
from sqlalchemy.orm import Session

from app import server_db
from app.config import resolve_data_dir, settings
from app.server_models import User


@pytest.fixture()
def file_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path}/budgeter.db")
    monkeypatch.setattr(settings, "data_dir", None)
    server_db.reset()
    yield tmp_path
    server_db.reset()


def test_resolve_data_dir_defaults_to_the_database_files_directory(file_mode):
    assert resolve_data_dir() == file_mode


def test_resolve_data_dir_prefers_the_explicit_setting(file_mode, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(file_mode / "d"))
    assert resolve_data_dir() == file_mode / "d"


def test_resolve_data_dir_is_none_for_the_in_memory_sentinel(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "sqlite://")
    monkeypatch.setattr(settings, "data_dir", None)
    assert resolve_data_dir() is None


def test_server_upgrade_creates_schema_and_is_idempotent(file_mode, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(file_mode / "nested"))
    server_db.upgrade_to_head()
    server_db.upgrade_to_head()

    conn = sqlite3.connect(file_mode / "nested" / "server.db")
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert {"users", "sessions", "server_settings", "alembic_version"} <= tables


def test_server_upgrade_skips_the_in_memory_sentinel(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "sqlite://")
    monkeypatch.setattr(settings, "data_dir", None)
    server_db.upgrade_to_head()  # would raise if it tried to run Alembic here


def test_new_user_defaults_to_active_admin(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "sqlite://")
    monkeypatch.setattr(settings, "data_dir", None)
    server_db.reset()
    try:
        with Session(server_db.get_engine()) as db:
            user = User(username="a", password_hash="x")
            db.add(user)
            db.commit()
            assert user.is_admin is True
            assert user.is_disabled is False
            assert user.api_key_hash is None
    finally:
        server_db.reset()

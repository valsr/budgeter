import sqlite3

import pytest

from app.errors import ValidationError
from app.services import backup as backup_svc


@pytest.fixture()
def real_db_path(tmp_path):
    path = str(tmp_path / "test.db")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE widgets (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO widgets (name) VALUES ('gadget')")
    conn.commit()
    conn.close()
    return path


class TestResolveSqlitePath:
    def test_relative_path(self):
        assert backup_svc.resolve_sqlite_path("sqlite:///./budgeter.db") == "./budgeter.db"

    def test_absolute_path(self):
        assert backup_svc.resolve_sqlite_path("sqlite:////var/data/budgeter.db") == "/var/data/budgeter.db"

    def test_non_sqlite_url_rejected(self):
        with pytest.raises(ValidationError):
            backup_svc.resolve_sqlite_path("postgresql://user:pass@host/db")


class TestCreateBackupBytes:
    def test_returns_valid_sqlite_bytes(self, real_db_path):
        data = backup_svc.create_backup_bytes(real_db_path)
        assert data.startswith(backup_svc.SQLITE_MAGIC)

    def test_backup_contains_same_data_as_source(self, real_db_path, tmp_path):
        data = backup_svc.create_backup_bytes(real_db_path)
        copy_path = tmp_path / "copy.db"
        copy_path.write_bytes(data)

        conn = sqlite3.connect(str(copy_path))
        rows = conn.execute("SELECT name FROM widgets").fetchall()
        conn.close()
        assert rows == [("gadget",)]


class TestValidateSqliteBytes:
    def test_valid_sqlite_passes(self, real_db_path):
        data = backup_svc.create_backup_bytes(real_db_path)
        backup_svc.validate_sqlite_bytes(data)  # should not raise

    def test_garbage_bytes_rejected(self):
        with pytest.raises(ValidationError):
            backup_svc.validate_sqlite_bytes(b"not a database at all")

    def test_empty_bytes_rejected(self):
        with pytest.raises(ValidationError):
            backup_svc.validate_sqlite_bytes(b"")

    def test_truncated_sqlite_header_rejected(self):
        # starts with the magic bytes but isn't a real, complete database
        fake = backup_svc.SQLITE_MAGIC + b"\x00" * 10
        with pytest.raises(ValidationError):
            backup_svc.validate_sqlite_bytes(fake)


class TestWriteBackupBytes:
    def test_round_trip_replaces_file_contents(self, real_db_path, tmp_path):
        # Create a second, different database and restore it over the first.
        other_path = str(tmp_path / "other.db")
        conn = sqlite3.connect(other_path)
        conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, label TEXT)")
        conn.execute("INSERT INTO items (label) VALUES ('restored')")
        conn.commit()
        conn.close()
        other_data = backup_svc.create_backup_bytes(other_path)

        backup_svc.write_backup_bytes(real_db_path, other_data)

        conn = sqlite3.connect(real_db_path)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        rows = conn.execute("SELECT label FROM items").fetchall()
        conn.close()
        assert "items" in tables
        assert "widgets" not in tables  # fully replaced, not merged
        assert rows == [("restored",)]

    def test_invalid_data_rejected_without_touching_existing_file(self, real_db_path):
        original = open(real_db_path, "rb").read()
        with pytest.raises(ValidationError):
            backup_svc.write_backup_bytes(real_db_path, b"garbage")
        assert open(real_db_path, "rb").read() == original

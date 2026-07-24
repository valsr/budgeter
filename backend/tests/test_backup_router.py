import io
import sqlite3

import pytest

from app import config as config_module
from app.services import backup as backup_svc


@pytest.fixture()
def file_backed_settings(monkeypatch, tmp_path):
    """Point the app at a real on-disk SQLite file so the backup endpoints
    (which manipulate the file directly) have something real to act on,
    instead of the in-memory `sqlite://` DB the rest of the test suite uses.
    """
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO accounts (name) VALUES ('Main checking')")
    conn.commit()
    conn.close()

    monkeypatch.setattr(config_module.settings, "database_url", f"sqlite:///{db_path}")
    return str(db_path)


def test_requires_auth(client):
    resp = client.get("/api/backup")
    assert resp.status_code == 401


def test_download_backup_returns_sqlite_file(client, auth_headers, file_backed_settings):
    resp = client.get("/api/backup", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.content.startswith(backup_svc.SQLITE_MAGIC)
    assert "attachment" in resp.headers["content-disposition"]


def test_downloaded_backup_contains_real_data(client, auth_headers, file_backed_settings, tmp_path):
    resp = client.get("/api/backup", headers=auth_headers)
    copy_path = tmp_path / "downloaded.db"
    copy_path.write_bytes(resp.content)

    conn = sqlite3.connect(str(copy_path))
    rows = conn.execute("SELECT name FROM accounts").fetchall()
    conn.close()
    assert rows == [("Main checking",)]


def test_restore_replaces_database_contents(client, auth_headers, file_backed_settings, tmp_path):
    other_path = tmp_path / "other.db"
    conn = sqlite3.connect(str(other_path))
    conn.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO accounts (name) VALUES ('Restored account')")
    conn.commit()
    conn.close()
    other_bytes = other_path.read_bytes()

    resp = client.post(
        "/api/backup/restore",
        headers=auth_headers,
        files={"file": ("backup.db", io.BytesIO(other_bytes), "application/octet-stream")},
    )
    assert resp.status_code == 204

    conn = sqlite3.connect(file_backed_settings)
    rows = conn.execute("SELECT name FROM accounts").fetchall()
    conn.close()
    assert rows == [("Restored account",)]


def test_restore_rejects_invalid_file(client, auth_headers, file_backed_settings):
    resp = client.post(
        "/api/backup/restore",
        headers=auth_headers,
        files={"file": ("bad.db", io.BytesIO(b"not a database"), "application/octet-stream")},
    )
    assert resp.status_code == 422

import pytest

from app import runtime
from app.services import server_config


@pytest.fixture(autouse=True)
def _no_runtime(monkeypatch):
    monkeypatch.setattr(runtime, "current", None)


@pytest.mark.parametrize("path", ["/health", "/api/health"])
def test_public_health_is_ok_and_says_little(anon, path):
    resp = anon.get(path)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "ok", "uptime_seconds": body["uptime_seconds"], "checks": {"server_db": "ok"}}
    assert isinstance(body["uptime_seconds"], int) and body["uptime_seconds"] >= 0


def test_public_health_is_503_when_the_server_database_is_unreachable(anon, monkeypatch):
    from app.routers import health

    def boom():
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(health, "_check_server_db", boom)
    resp = anon.get("/health")
    assert resp.status_code == 503
    assert resp.json()["status"] == "error"
    assert resp.json()["checks"] == {"server_db": "error"}  # no internals leaked to the public
    assert "disk on fire" not in resp.text


def test_detailed_health_is_admin_only(client, auth_headers, test_user, server_session):
    assert client.get("/api/admin/health").status_code == 401
    test_user.is_admin = False
    server_session.commit()
    assert client.get("/api/admin/health", headers=auth_headers).status_code == 403


def test_detailed_health_in_memory(client, auth_headers):
    body = client.get("/api/admin/health", headers=auth_headers).json()
    assert body["status"] == "ok"
    assert body["checks"] == {"server_db": "ok", "books": "ok", "ssl": "disabled"}
    assert body["users"] == {"total": 1, "active_admins": 1, "disabled": 0}
    assert body["serving"] is None  # not started through the launcher
    assert body["python_version"].count(".") == 2
    assert body["uptime_seconds"] >= 0 and body["started_at"]


def test_detailed_health_reports_files_schema_and_serving(make_client, files, monkeypatch):
    admin = make_client("admin")
    make_client("bob")
    admin.patch("/api/admin/users/2", json={"is_disabled": True})
    monkeypatch.setattr(runtime, "current", runtime.Runtime(port=8000, ssl_certfile=None, ssl_keyfile=None))

    body = admin.get("/api/admin/health").json()

    assert body["status"] == "ok"
    assert body["data_dir"] == str(files)
    assert body["users"] == {"total": 2, "active_admins": 1, "disabled": 1}
    assert body["storage"]["books_files"] == 2
    assert body["storage"]["books_bytes"] > 0 and body["storage"]["server_db_bytes"] > 0
    assert body["schema"] == {"server": "9f2c4d7a1e55", "books": "b27eace77f79"}
    assert body["serving"] == {"port": 8000, "https": False}


def test_detailed_health_flags_a_saved_certificate_that_has_gone(make_client, files, tmp_path):
    from tests.test_server_config import make_cert
    from app import server_db

    admin = make_client("admin")
    cert, key = make_cert(tmp_path)
    with server_db.SessionLocal() as sdb:
        server_config.update(sdb, ssl_enabled=True, ssl_certfile=str(cert), ssl_keyfile=str(key))
    assert admin.get("/api/admin/health").json()["checks"]["ssl"] == "ok"

    cert.unlink()
    body = admin.get("/api/admin/health").json()
    assert body["status"] == "degraded"
    assert "Certificate file not found" in body["checks"]["ssl"]


def test_detailed_health_flags_a_broken_books_file(make_client, files):
    from app import books

    admin = make_client("admin")
    bob = make_client("bob")
    books.dispose_all()
    books.books_path(bob.user_id).write_bytes(b"garbage")
    body = admin.get("/api/admin/health").json()
    assert body["status"] == "degraded"
    assert body["checks"]["books"] == "1 of 2 books files can't be read"

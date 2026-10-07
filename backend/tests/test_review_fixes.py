"""Regression tests for the defects the whole-branch review found."""

import sqlite3
import threading
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import books, server_db
from app.errors import AuthError
from app.main import resolve_static_path
from app.server_models import User, UserSession, utcnow
from app.services import users


# --- C1: a deleted user's id (and so their sessions/books) is never reused ---


def test_user_ids_are_never_reused(server_session):
    users.create_user(server_session, "admin", "password1")
    bob = users.create_user(server_session, "bob", "password1")
    bob_id = bob.id
    users.delete_user(server_session, bob_id)
    carol = users.create_user(server_session, "carol", "password1")
    assert carol.id != bob_id


def test_user_ids_are_never_reused_in_a_migrated_database(files):
    with server_db.SessionLocal() as sdb:
        users.create_user(sdb, "admin", "password1")
        bob_id = users.create_user(sdb, "bob", "password1").id
        users.delete_user(sdb, bob_id)
        assert users.create_user(sdb, "carol", "password1").id != bob_id


def test_a_login_racing_a_delete_cannot_leave_a_session_behind(server_session):
    users.create_user(server_session, "admin", "password1")
    bob = users.create_user(server_session, "bob", "password1")
    assert bob.id  # loaded: the in-flight login has already looked bob up
    with Session(server_db.get_engine()) as other:  # ...when an admin deletes him
        users.delete_user(other, bob.id)

    with pytest.raises(AuthError, match="Invalid username or password"):
        users.create_session(server_session, bob)
    assert server_session.execute(select(UserSession)).scalars().all() == []


def test_a_session_whose_user_is_gone_is_removed_not_kept(server_session):
    bob = users.create_user(server_session, "bob", "password1")
    token = users.create_session(server_session, bob)
    # Bypass delete_user, as a database restored from elsewhere might have.
    server_session.commit()
    connection = server_session.connection()
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    connection.execute(User.__table__.delete().where(User.id == bob.id))
    server_session.commit()
    server_session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
    server_session.expire_all()
    assert users.resolve_session(server_session, token)[0] is None
    assert server_session.execute(select(UserSession)).scalars().all() == []


def test_deleted_users_cookie_never_becomes_the_next_users(make_client):
    admin = make_client("admin")
    bob = make_client("bob")
    assert admin.delete(f"/api/admin/users/{bob.user_id}").status_code == 204
    carol = make_client("carol")
    assert carol.user_id != bob.user_id
    assert bob.get("/api/auth/me").status_code == 401


# --- C2: the SPA fallback must not serve files outside the static directory ---


def test_static_fallback_cannot_escape_the_static_directory(tmp_path):
    static = tmp_path / "app" / "static"
    static.mkdir(parents=True)
    (static / "index.html").write_text("<html>")
    (static / "favicon.svg").write_text("<svg>")
    secret = tmp_path / "data" / "server.db"
    secret.parent.mkdir()
    secret.write_text("password hashes")

    index = static / "index.html"
    assert resolve_static_path(static, "favicon.svg") == static / "favicon.svg"
    assert resolve_static_path(static, "") == index
    assert resolve_static_path(static, "accounts") == index  # client-side route
    for hostile in ("../../data/server.db", "../static/../../data/server.db", str(secret), "assets/../../../data/server.db"):
        assert resolve_static_path(static, hostile) == index, hostile


# --- I1: a restore that can't become usable books is refused before the swap ---


def _fake_books(tmp_path, revision: str) -> bytes:
    path = tmp_path / f"fake-{revision}.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE accounts (x INTEGER)")
    conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
    conn.execute("INSERT INTO alembic_version VALUES (?)", (revision,))
    conn.commit()
    conn.close()
    return path.read_bytes()


@pytest.mark.parametrize("revision", ["b27eace77f79", "5928280a1455"])
def test_restore_refuses_a_lookalike_that_is_not_real_books(make_client, tmp_path, revision):
    alice = make_client("alice")
    assert alice.post("/api/accounts", json={"name": "Keep me", "type": "asset"}).status_code == 201
    path = books.books_path(alice.user_id)
    before = path.read_bytes()

    resp = alice.post(
        "/api/backup/restore",
        files={"file": ("b.db", _fake_books(tmp_path, revision), "application/octet-stream")},
    )

    assert resp.status_code == 422
    assert path.read_bytes() == before
    assert [a["name"] for a in alice.get("/api/accounts").json()] == ["Keep me"]
    assert sorted(p.name for p in path.parent.iterdir()) == [path.name]  # no staging leftovers


def test_whole_server_restore_refuses_lookalike_books(make_client, tmp_path, files):
    import io
    import zipfile

    from app.errors import ValidationError
    from app.services import server_backup

    alice = make_client("alice")
    archive = server_backup.create_archive()
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(archive)) as src, zipfile.ZipFile(out, "w") as dst:
        dst.writestr("server.db", src.read("server.db"))
        dst.writestr(f"books/{alice.user_id}.db", _fake_books(tmp_path, "b27eace77f79"))
    before = {p: p.read_bytes() for p in files.rglob("*") if p.is_file()}

    with pytest.raises(ValidationError):
        server_backup.restore_archive(out.getvalue())

    assert {p: p.read_bytes() for p in files.rglob("*") if p.is_file()} == before


def test_startup_survives_one_users_broken_books(make_client, files):
    from fastapi.testclient import TestClient

    from app.main import app

    alice, bob = make_client("alice"), make_client("bob")
    assert bob.post("/api/accounts", json={"name": "Bob savings", "type": "asset"}).status_code == 201
    books.dispose_all()
    books.books_path(alice.user_id).write_bytes(b"this is not a database at all")

    with TestClient(app) as restarted:  # runs the lifespan, i.e. a server start
        restarted.cookies = bob.cookies
        assert [a["name"] for a in restarted.get("/api/accounts").json()] == ["Bob savings"]


# --- I2: nothing keeps reading or writing a replaced file ---


def test_requests_after_a_restore_use_the_new_file_even_with_sessions_open(make_client):
    alice = make_client("alice")
    empty = alice.get("/api/backup").content
    assert alice.post("/api/accounts", json={"name": "Old", "type": "asset"}).status_code == 201

    lingering = books.session_for(alice.user_id)  # e.g. a background task mid-flight
    try:
        lingering.execute(select(1)).all()
        resp = alice.post("/api/backup/restore", files={"file": ("b.db", empty, "application/octet-stream")})
        assert resp.status_code == 204
        assert alice.post("/api/accounts", json={"name": "New", "type": "asset"}).status_code == 201
    finally:
        lingering.close()

    conn = sqlite3.connect(books.books_path(alice.user_id))
    names = [r[0] for r in conn.execute("SELECT name FROM accounts")]
    conn.close()
    assert names == ["New"]  # the write landed in the file that's actually on disk


def test_concurrent_books_creation_migrates_every_file(files):
    errors: list[BaseException] = []

    def create(user_id: int) -> None:
        try:
            books.create_books(user_id)
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=create, args=(i,)) for i in range(20, 28)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    for user_id in range(20, 28):
        conn = sqlite3.connect(books.books_path(user_id))
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        conn.close()
        assert {"accounts", "transactions", "app_settings"} <= tables, user_id
        assert revision == "b27eace77f79", user_id


# --- I3: state-changing requests from another origin are refused ---


def test_unsafe_requests_from_a_foreign_origin_are_refused(client, auth_headers):
    payload = {"name": "x", "type": "asset"}
    evil = {**auth_headers, "Origin": "http://localhost:9999"}
    resp = client.post("/api/accounts", json=payload, headers=evil)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Cross-origin request refused"
    assert client.get("/api/accounts", headers=auth_headers).json() == []

    # Multipart forms are what a hostile page can actually send without a preflight.
    resp = client.post(
        "/api/admin/backup/restore", headers=evil, files={"file": ("a.zip", b"zip", "application/zip")}
    )
    assert resp.status_code == 403

    for origin in ("http://localhost:5173", "http://testserver", "https://testserver"):
        ok = client.post("/api/accounts", json=payload, headers={**auth_headers, "Origin": origin})
        assert ok.status_code == 201, origin
    # No Origin at all: curl, scripts, the MCP adapter.
    assert client.post("/api/accounts", json=payload, headers=auth_headers).status_code == 201
    # Reads are never blocked.
    assert client.get("/api/accounts", headers=evil).status_code == 200


def test_login_from_a_foreign_origin_is_refused(anon):
    resp = anon.post(
        "/api/auth/register",
        json={"username": "alice", "password": "password1"},
        headers={"Origin": "https://evil.example"},
    )
    assert resp.status_code == 403


# --- I4: a renewed session renews the browser's cookie too ---


def test_sliding_renewal_reissues_the_cookie(anon, server_session):
    anon.post("/api/auth/register", json={"username": "alice", "password": "password1"})
    fresh = anon.get("/api/auth/me")
    assert "set-cookie" not in fresh.headers  # nothing to renew yet

    row = server_session.execute(select(UserSession)).scalar_one()
    row.expires_at = utcnow() + timedelta(days=10)
    server_session.commit()

    renewed = anon.get("/api/auth/me")
    assert renewed.status_code == 200
    cookie = renewed.headers["set-cookie"]
    assert "budgeter_session=" in cookie and "Max-Age=2592000" in cookie and "HttpOnly" in cookie
    server_session.expire_all()
    assert row.expires_at > utcnow() + timedelta(days=29)

import os

os.environ.setdefault("BUDGETER_DATABASE_URL", "sqlite://")

import pytest
from fastapi.testclient import TestClient

from app import books, server_db
from app.config import settings
from app.db import get_db
from app.main import app
from app import runtime, security
from app.security import hash_token
from app.server_models import User


# Real scrypt costs ~40ms per hash, on every registration and login the suite performs. The cost
# travels inside each stored hash, so verification still works; test_security checks the real one.
security._SCRYPT_N = 2


@pytest.fixture(autouse=True)
def _no_runtime(monkeypatch):
    """Tests run as if started outside the launcher, unless one says otherwise."""
    monkeypatch.setattr(runtime, "current", None)


@pytest.fixture()
def server_session():
    """A session on a fresh in-memory server database. Requests open their
    own sessions on the same engine, so `expire_all()` (or a fresh query)
    is needed to see what a request changed."""
    server_db.reset()
    books.dispose_all()
    session = server_db.SessionLocal()
    try:
        yield session
    finally:
        session.close()
        server_db.reset()
        books.dispose_all()


@pytest.fixture()
def test_user(server_session):
    """The account behind `auth_headers`. Its password hash is deliberately
    unusable: hashing a real one costs ~50ms, on every test that wants a client."""
    user = User(username="tester", password_hash="!", api_key_hash=hash_token("test-api-key"))
    server_session.add(user)
    server_session.commit()
    return user


@pytest.fixture()
def db_session(test_user):
    """The fixture user's (in-memory) books."""
    session = books.session_for(test_user.id)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def anon(server_session):
    """A client with no account behind it -- for exercising registration,
    login and everything that must reject an unauthenticated caller."""
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def client(anon, test_user, db_session):
    """A client for the fixture user (send `auth_headers`). Requests share
    the test's own `db_session` rather than opening one per request, so a
    test can read back what a request wrote without refreshing anything."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return anon


@pytest.fixture()
def files(tmp_path, monkeypatch):
    """File-backed mode: a real data directory under tmp_path, with the
    server database migrated. For anything that is about the files
    themselves -- per-user books, the legacy claim, backup and restore."""
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path}/budgeter.db")
    monkeypatch.setattr(settings, "data_dir", None)
    server_db.reset()
    books.dispose_all()
    server_db.upgrade_to_head()
    yield tmp_path
    server_db.reset()
    books.dispose_all()


@pytest.fixture()
def make_client(files):
    """Factory for independent browser-like clients (each with its own
    cookie jar) against the file-backed app."""

    def make(username: str | None = None, password: str = "password1") -> TestClient:
        c = TestClient(app)
        if username is not None:
            resp = c.post("/api/auth/register", json={"username": username, "password": password})
            assert resp.status_code == 201, resp.text
            c.user_id = resp.json()["id"]
        return c

    return make


@pytest.fixture()
def auth_headers():
    return {"Authorization": "Bearer test-api-key"}

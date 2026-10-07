import os

os.environ.setdefault("BUDGETER_DATABASE_URL", "sqlite://")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import db as db_module
from app import server_db
from app.db import Base, get_db
from app.main import app
from app.security import hash_token
from app.server_models import User

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def server_session():
    """A session on a fresh in-memory server database. Requests open their
    own sessions on the same engine, so `expire_all()` (or a fresh query)
    is needed to see what a request changed."""
    server_db.reset()
    session = server_db.SessionLocal()
    try:
        yield session
    finally:
        session.close()
        server_db.reset()


@pytest.fixture()
def anon(db_session, server_session, monkeypatch):
    """A client with no account behind it -- for exercising registration,
    login and everything that must reject an unauthenticated caller."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    # Background tasks (see services/categorization.py) open their own
    # session via app.db.SessionLocal rather than reusing the request's —
    # point that at the same test engine/pool so they see the same data.
    monkeypatch.setattr(db_module, "SessionLocal", TestingSessionLocal)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def test_user(server_session):
    """The account behind `auth_headers`. Its password hash is deliberately
    unusable: hashing a real one costs ~50ms, on every test that wants a client."""
    user = User(username="tester", password_hash="!", api_key_hash=hash_token("test-api-key"))
    server_session.add(user)
    server_session.commit()
    return user


@pytest.fixture()
def client(anon, test_user):
    return anon


@pytest.fixture()
def auth_headers():
    return {"Authorization": "Bearer test-api-key"}

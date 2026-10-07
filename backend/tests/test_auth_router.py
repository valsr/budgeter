from datetime import timedelta

from sqlalchemy import select

from app.server_models import User, UserSession, utcnow
from app.services import users

ALICE = {"username": "alice", "password": "password1"}


def register(client, username="alice", password="password1"):
    resp = client.post("/api/auth/register", json={"username": username, "password": password})
    assert resp.status_code == 201, resp.text
    return resp


def test_status_reports_no_users_then_users(anon):
    assert anon.get("/api/auth/status").json() == {"registration_open": True, "has_users": False}
    register(anon)
    anon.cookies.clear()
    assert anon.get("/api/auth/status").json() == {"registration_open": True, "has_users": True}


def test_register_logs_in_and_me_returns_the_user(anon):
    resp = register(anon, username="  Alice ")
    body = resp.json()
    assert body == {"id": body["id"], "username": "alice", "is_admin": True}
    cookie = resp.headers["set-cookie"]
    assert "budgeter_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/" in cookie
    assert "Max-Age=2592000" in cookie
    assert "Secure" not in cookie  # plain http in tests
    assert anon.get("/api/auth/me").json() == body


def test_session_cookie_is_secure_over_https(anon):
    resp = anon.post("https://testserver/api/auth/register", json=ALICE)
    assert "Secure" in resp.headers["set-cookie"]


def test_me_requires_a_session(anon):
    assert anon.get("/api/auth/me").status_code == 401


def test_register_conflict_is_409_and_bad_input_422(anon):
    register(anon)
    anon.cookies.clear()
    resp = anon.post("/api/auth/register", json={"username": "ALICE", "password": "password2"})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Username is already taken"

    resp = anon.post("/api/auth/register", json={"username": "x", "password": "password1"})
    assert resp.status_code == 422
    assert "Username must be 3–32 characters" in resp.json()["detail"]

    for bad_password in ["short", "x" * 257]:
        resp = anon.post("/api/auth/register", json={"username": "bob", "password": bad_password})
        assert resp.status_code == 422
        assert "Password must be 8–256 characters" in resp.json()["detail"]
    assert "set-cookie" not in resp.headers


def test_register_is_403_when_closed(anon, server_session):
    users.set_registration_open(server_session, False)
    register(anon)  # no users yet: still allowed
    anon.cookies.clear()
    resp = anon.post("/api/auth/register", json={"username": "bob", "password": "password1"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Registration is closed"
    assert anon.get("/api/auth/status").json() == {"registration_open": False, "has_users": True}


def test_login_wrong_password_unknown_user_and_disabled_are_the_same_401(anon, server_session):
    register(anon)
    register(anon, username="bob")
    anon.cookies.clear()
    bob = server_session.execute(select(User).where(User.username == "bob")).scalar_one()
    users.update_user(server_session, bob.id, is_disabled=True)

    for creds in [
        {"username": "alice", "password": "wrong-password"},
        {"username": "nobody", "password": "password1"},
        {"username": "bob", "password": "password1"},
    ]:
        resp = anon.post("/api/auth/login", json=creds)
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Invalid username or password"}
        assert "set-cookie" not in resp.headers

    resp = anon.post("/api/auth/login", json={"username": " Alice ", "password": "password1"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "alice"
    assert anon.get("/api/auth/me").status_code == 200


def test_logout_ends_the_session(anon, server_session):
    register(anon)
    token = anon.cookies.get("budgeter_session")
    resp = anon.post("/api/auth/logout")
    assert resp.status_code == 204
    assert anon.get("/api/auth/me").status_code == 401
    # Not just a cleared cookie: the token itself is dead.
    anon.cookies.set("budgeter_session", token)
    assert anon.get("/api/auth/me").status_code == 401
    assert server_session.execute(select(UserSession)).scalars().all() == []


def test_expired_session_is_401(anon, server_session):
    register(anon)
    row = server_session.execute(select(UserSession)).scalar_one()
    row.expires_at = utcnow() - timedelta(seconds=1)
    server_session.commit()
    assert anon.get("/api/auth/me").status_code == 401


def test_password_change_keeps_this_session_and_ends_others(anon):
    register(anon)
    first = anon.cookies.get("budgeter_session")
    anon.cookies.clear()
    anon.post("/api/auth/login", json=ALICE)
    second = anon.cookies.get("budgeter_session")
    assert first != second

    resp = anon.post("/api/auth/password", json={"current_password": "nope-nope", "new_password": "password2"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Current password is incorrect"
    assert anon.get("/api/auth/me").status_code == 200  # a typo doesn't cost the session
    resp = anon.post("/api/auth/password", json={"current_password": "password1", "new_password": "short"})
    assert resp.status_code == 422

    resp = anon.post("/api/auth/password", json={"current_password": "password1", "new_password": "password2"})
    assert resp.status_code == 204
    assert anon.get("/api/auth/me").status_code == 200  # this session survives

    anon.cookies.set("budgeter_session", first)
    assert anon.get("/api/auth/me").status_code == 401  # the other one doesn't
    anon.cookies.clear()
    assert anon.post("/api/auth/login", json=ALICE).status_code == 401
    assert anon.post("/api/auth/login", json={"username": "alice", "password": "password2"}).status_code == 200


def test_api_key_is_shown_once_and_replaces_the_old(anon):
    register(anon)
    assert anon.get("/api/settings/api-key").json() == {"has_key": False}

    key = anon.post("/api/settings/api-key/regenerate").json()["api_key"]
    assert anon.get("/api/settings/api-key").json() == {"has_key": True}

    anon.cookies.clear()
    bearer = {"Authorization": f"Bearer {key}"}
    assert anon.get("/api/auth/me", headers=bearer).json()["username"] == "alice"

    new_key = anon.post("/api/settings/api-key/regenerate", headers=bearer).json()["api_key"]
    assert anon.get("/api/auth/me", headers=bearer).status_code == 401
    assert anon.get("/api/auth/me", headers={"Authorization": f"Bearer {new_key}"}).status_code == 200


def test_existing_endpoints_accept_the_session_cookie(anon):
    assert anon.get("/api/accounts").status_code == 401
    register(anon)
    assert anon.get("/api/accounts").status_code == 200

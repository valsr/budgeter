from fastapi import APIRouter, Depends

from app.auth import current_user, require_admin
from app.main import app
from app.server_models import User

_test_router = APIRouter()


@_test_router.get("/protected")
def protected(user: User = Depends(current_user)) -> dict[str, str]:
    return {"user": user.username}


@_test_router.get("/admin-only")
def admin_only(user: User = Depends(require_admin)) -> dict[str, str]:
    return {"user": user.username}


app.include_router(_test_router)


def test_protected_requires_valid_key(client):
    resp = client.get("/protected")
    assert resp.status_code == 401

    resp = client.get("/protected", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401

    resp = client.get("/protected", headers={"Authorization": "Bearer test-api-key"})
    assert resp.status_code == 200
    assert resp.json() == {"user": "tester"}


def test_env_default_key_no_longer_authenticates(client):
    # conftest sets BUDGETER_API_KEY=test-api-key, which is also the fixture
    # user's key -- so prove the point with a server that has no users.
    resp = client.get("/protected", headers={"Authorization": "Bearer dev-local-api-key"})
    assert resp.status_code == 401


def test_env_key_grants_nothing_without_a_matching_user(anon):
    resp = anon.get("/protected", headers={"Authorization": "Bearer test-api-key"})
    assert resp.status_code == 401


def test_a_bad_bearer_key_does_not_fall_back_to_the_session_cookie(anon):
    anon.post("/api/auth/register", json={"username": "alice", "password": "password1"})
    assert anon.get("/protected").status_code == 200
    assert anon.get("/protected", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_a_garbage_session_cookie_is_401(anon):
    anon.cookies.set("budgeter_session", "not-a-real-token")
    assert anon.get("/protected").status_code == 401


def test_non_admin_gets_403_from_require_admin(client, test_user, server_session, auth_headers):
    assert client.get("/admin-only", headers=auth_headers).status_code == 200
    assert client.get("/admin-only").status_code == 401

    test_user.is_admin = False
    server_session.commit()
    resp = client.get("/admin-only", headers=auth_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Admin access required"

import pytest

from app import books


@pytest.fixture()
def admin(make_client):
    return make_client("admin")


def user_list(client):
    resp = client.get("/api/admin/users")
    assert resp.status_code == 200, resp.text
    return resp.json()


def login(make_client, username, password="password1"):
    c = make_client()
    return c, c.post("/api/auth/login", json={"username": username, "password": password})


def delete_me(client, password):
    return client.request("DELETE", "/api/auth/me", json={"password": password})


def test_admin_endpoints_need_admin(make_client, admin):
    bob = make_client("bob")
    assert admin.patch(f"/api/admin/users/{bob.user_id}", json={"is_admin": False}).status_code == 200
    anonymous = make_client()
    calls = [
        ("GET", "/api/admin/users", None),
        ("POST", "/api/admin/users", {"username": "eve", "password": "password1"}),
        ("PATCH", f"/api/admin/users/{admin.user_id}", {"is_disabled": True}),
        ("DELETE", f"/api/admin/users/{admin.user_id}", None),
        ("GET", "/api/admin/settings", None),
        ("PATCH", "/api/admin/settings", {"registration_open": False}),
    ]
    for method, url, body in calls:
        assert bob.request(method, url, json=body).status_code == 403, (method, url)
        assert anonymous.request(method, url, json=body).status_code == 401, (method, url)
    assert [u["username"] for u in user_list(admin)] == ["admin", "bob"]


def test_list_create_and_patch_users(admin):
    resp = admin.post("/api/admin/users", json={"username": " Carol ", "password": "password1"})
    assert resp.status_code == 201, resp.text
    carol = resp.json()
    assert carol == {
        "id": carol["id"],
        "username": "carol",
        "is_admin": True,
        "is_disabled": False,
        "created_at": carol["created_at"],
    }
    assert books.books_path(carol["id"]).exists()
    assert [u["username"] for u in user_list(admin)] == ["admin", "carol"]
    assert "password_hash" not in user_list(admin)[0] and "api_key_hash" not in user_list(admin)[0]

    resp = admin.patch(f"/api/admin/users/{carol['id']}", json={"is_admin": False})
    assert resp.status_code == 200
    assert resp.json()["is_admin"] is False and resp.json()["is_disabled"] is False

    assert admin.post("/api/admin/users", json={"username": "carol", "password": "password1"}).status_code == 409
    assert admin.post("/api/admin/users", json={"username": "x", "password": "password1"}).status_code == 422
    assert admin.patch(f"/api/admin/users/{carol['id']}", json={"password": "short"}).status_code == 422
    assert admin.patch("/api/admin/users/999", json={"is_admin": True}).status_code == 404
    assert admin.delete("/api/admin/users/999").status_code == 404


def test_reset_password_lets_the_user_log_in_with_the_new_one(make_client, admin):
    bob = make_client("bob")
    resp = admin.patch(f"/api/admin/users/{bob.user_id}", json={"password": "brand-new-pw"})
    assert resp.status_code == 200
    assert bob.get("/api/auth/me").status_code == 401  # the old session is gone
    assert login(make_client, "bob")[1].status_code == 401
    assert login(make_client, "bob", "brand-new-pw")[1].status_code == 200


def test_disable_blocks_login_session_and_key_and_enable_restores(make_client, admin):
    bob = make_client("bob")
    key = bob.post("/api/settings/api-key/regenerate").json()["api_key"]
    bearer = {"Authorization": f"Bearer {key}"}
    anonymous = make_client()

    assert admin.patch(f"/api/admin/users/{bob.user_id}", json={"is_disabled": True}).json()["is_disabled"] is True
    assert bob.get("/api/accounts").status_code == 401
    assert anonymous.get("/api/accounts", headers=bearer).status_code == 401
    assert login(make_client, "bob")[1].status_code == 401

    assert admin.patch(f"/api/admin/users/{bob.user_id}", json={"is_disabled": False}).status_code == 200
    assert anonymous.get("/api/accounts", headers=bearer).status_code == 200
    assert login(make_client, "bob")[1].status_code == 200


def test_last_admin_guards_return_409(make_client, admin):
    bob = make_client("bob")
    admin.patch(f"/api/admin/users/{bob.user_id}", json={"is_admin": False})
    me = f"/api/admin/users/{admin.user_id}"
    message = "The last active admin can't be demoted, disabled or deleted"
    resp = admin.patch(me, json={"is_admin": False})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "You can't remove your own admin rights"
    for resp in (
        admin.patch(me, json={"is_disabled": True}),
        admin.delete(me),
        delete_me(admin, "password1"),
    ):
        assert resp.status_code == 409
        assert resp.json()["detail"] == message
    assert admin.get("/api/auth/me").status_code == 200
    assert books.books_path(admin.user_id).exists()


def test_delete_user_removes_their_books_file(make_client, admin):
    bob = make_client("bob")
    path = books.books_path(bob.user_id)
    assert path.exists()
    assert admin.delete(f"/api/admin/users/{bob.user_id}").status_code == 204
    assert not path.exists()
    assert [u["username"] for u in user_list(admin)] == ["admin"]


def test_delete_me_needs_the_password(make_client, admin):
    bob = make_client("bob")
    path = books.books_path(bob.user_id)

    resp = delete_me(bob, "wrong-password")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Password is incorrect"
    assert path.exists()

    resp = delete_me(bob, "password1")
    assert resp.status_code == 204
    assert not path.exists()
    assert bob.get("/api/auth/me").status_code == 401
    assert login(make_client, "bob")[1].status_code == 401
    assert [u["username"] for u in user_list(admin)] == ["admin"]


def test_deleted_users_session_and_key_get_401_and_no_books_reappear(make_client, admin):
    bob = make_client("bob")
    key = bob.post("/api/settings/api-key/regenerate").json()["api_key"]
    bob.get("/api/accounts")  # an engine on bob's books is now cached
    path = books.books_path(bob.user_id)
    anonymous = make_client()

    assert admin.delete(f"/api/admin/users/{bob.user_id}").status_code == 204

    assert bob.get("/api/accounts").status_code == 401
    assert bob.post("/api/accounts", json={"name": "x", "type": "asset"}).status_code == 401
    assert anonymous.get("/api/accounts", headers={"Authorization": f"Bearer {key}"}).status_code == 401
    assert bob.get("/api/backup").status_code == 401
    assert not path.exists()


def test_closing_registration_blocks_register_but_not_admin_create(make_client, admin):
    assert admin.get("/api/admin/settings").json()["registration_open"] is True
    resp = admin.patch("/api/admin/settings", json={"registration_open": False})
    assert resp.status_code == 200
    assert resp.json()["registration_open"] is False
    assert resp.json()["port"] == 8000  # untouched by a registration-only update

    anonymous = make_client()
    assert anonymous.get("/api/auth/status").json() == {"registration_open": False, "has_users": True}
    resp = anonymous.post("/api/auth/register", json={"username": "eve", "password": "password1"})
    assert resp.status_code == 403

    assert admin.post("/api/admin/users", json={"username": "dave", "password": "password1"}).status_code == 201
    assert login(make_client, "dave")[1].status_code == 200


def test_an_admin_cannot_remove_their_own_admin_rights(make_client, admin):
    bob = make_client("bob")  # a second admin, so this isn't the last-admin guard talking
    me = f"/api/admin/users/{admin.user_id}"

    resp = admin.patch(me, json={"is_admin": False})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "You can't remove your own admin rights"
    assert admin.get("/api/admin/users").status_code == 200  # still an admin

    # Other changes to yourself still go through, as does setting it to what it already is.
    assert admin.patch(me, json={"is_admin": True}).status_code == 200
    assert admin.patch(me, json={"password": "another-password"}).status_code == 200

    # Another admin can do it.
    assert bob.patch(me, json={"is_admin": False}).status_code == 200


def test_server_settings_cover_port_and_ssl(make_client, admin, tmp_path, monkeypatch):
    from app import runtime
    from tests.test_server_config import make_cert

    monkeypatch.setattr(runtime, "current", None)
    assert admin.get("/api/admin/settings").json() == {
        "registration_open": True,
        "port": 8000,
        "ssl_enabled": False,
        "ssl_certfile": None,
        "ssl_keyfile": None,
        "managed": False,
        "restart_required": False,
        "port_override": None,
        "ssl_disabled_override": False,
    }

    # A partial update leaves everything else alone.
    resp = admin.patch("/api/admin/settings", json={"port": 8443})
    assert resp.status_code == 200
    assert resp.json()["port"] == 8443 and resp.json()["registration_open"] is True

    resp = admin.patch("/api/admin/settings", json={"port": 70000})
    assert resp.status_code == 422
    resp = admin.patch(
        "/api/admin/settings",
        json={"ssl_enabled": True, "ssl_certfile": str(tmp_path / "no.crt"), "ssl_keyfile": str(tmp_path / "no.key")},
    )
    assert resp.status_code == 422
    assert "Certificate file not found" in resp.json()["detail"]
    assert admin.get("/api/admin/settings").json()["ssl_enabled"] is False

    cert, key = make_cert(tmp_path)
    resp = admin.patch(
        "/api/admin/settings", json={"ssl_enabled": True, "ssl_certfile": str(cert), "ssl_keyfile": str(key)}
    )
    assert resp.status_code == 200 and resp.json()["ssl_enabled"] is True


def test_server_settings_say_when_a_restart_is_needed(admin, monkeypatch):
    from app import runtime

    monkeypatch.setattr(runtime, "current", runtime.Runtime(port=8000, ssl_certfile=None, ssl_keyfile=None))
    body = admin.get("/api/admin/settings").json()
    assert body["managed"] is True and body["restart_required"] is False

    body = admin.patch("/api/admin/settings", json={"port": 8443}).json()
    assert body["restart_required"] is True
    body = admin.patch("/api/admin/settings", json={"port": 8000}).json()
    assert body["restart_required"] is False

def test_requires_auth(client):
    resp = client.get("/api/settings/api-key")
    assert resp.status_code == 401


def test_api_key_status_never_returns_the_key(client, auth_headers):
    resp = client.get("/api/settings/api-key", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"has_key": True}


def test_regenerate_returns_new_key_and_invalidates_old_one(client, auth_headers):
    resp = client.post("/api/settings/api-key/regenerate", headers=auth_headers)
    assert resp.status_code == 200
    new_key = resp.json()["api_key"]
    assert new_key != "test-api-key"

    # the old key no longer authenticates...
    resp = client.get("/api/settings/api-key", headers=auth_headers)
    assert resp.status_code == 401

    # ...but the newly issued one does.
    new_headers = {"Authorization": f"Bearer {new_key}"}
    resp = client.get("/api/settings/api-key", headers=new_headers)
    assert resp.status_code == 200
    assert resp.json() == {"has_key": True}

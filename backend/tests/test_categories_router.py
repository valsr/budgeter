def test_requires_auth(client):
    resp = client.get("/api/categories")
    assert resp.status_code == 401


def test_create_and_list_categories(client, auth_headers):
    resp = client.post("/api/categories", json={"name": "shared"}, headers=auth_headers)
    assert resp.status_code == 201
    parent = resp.json()
    assert parent["parent_id"] is None
    assert parent["color"].startswith("#")

    resp = client.post(
        "/api/categories",
        json={"name": "groceries", "parent_id": parent["id"]},
        headers=auth_headers,
    )
    assert resp.status_code == 201

    resp = client.get("/api/categories", headers=auth_headers)
    assert resp.status_code == 200
    tree = resp.json()
    assert len(tree) == 1
    assert tree[0]["name"] == "shared"
    assert len(tree[0]["children"]) == 1
    assert tree[0]["children"][0]["name"] == "groceries"


def test_create_supports_arbitrary_depth(client, auth_headers):
    parent = client.post("/api/categories", json={"name": "shared"}, headers=auth_headers).json()
    child = client.post(
        "/api/categories", json={"name": "groceries", "parent_id": parent["id"]}, headers=auth_headers
    ).json()
    resp = client.post(
        "/api/categories", json={"name": "alcohol", "parent_id": child["id"]}, headers=auth_headers
    )
    assert resp.status_code == 201
    grandchild = resp.json()
    assert grandchild["parent_id"] == child["id"]

    tree = client.get("/api/categories", headers=auth_headers).json()
    assert tree[0]["children"][0]["children"][0]["name"] == "alcohol"


def test_resolve_path_creates_missing_segments_and_reuses_existing(client, auth_headers):
    shared = client.post("/api/categories", json={"name": "shared"}, headers=auth_headers).json()

    resp = client.post("/api/categories/resolve", json={"path": "shared:groceries:alcohol"}, headers=auth_headers)
    assert resp.status_code == 200
    leaf = resp.json()
    assert leaf["name"] == "alcohol"

    tree = client.get("/api/categories", headers=auth_headers).json()
    assert len(tree) == 1
    assert tree[0]["id"] == shared["id"]
    assert tree[0]["children"][0]["name"] == "groceries"
    assert tree[0]["children"][0]["children"][0]["name"] == "alcohol"

    # resolving again returns the same leaf, no duplicates created
    resp2 = client.post("/api/categories/resolve", json={"path": "shared:groceries:alcohol"}, headers=auth_headers)
    assert resp2.json()["id"] == leaf["id"]


def test_resolve_path_rejects_empty_segments_422(client, auth_headers):
    resp = client.post("/api/categories/resolve", json={"path": "shared::groceries"}, headers=auth_headers)
    assert resp.status_code == 422


def test_resolve_path_requires_auth(client):
    resp = client.post("/api/categories/resolve", json={"path": "shared"})
    assert resp.status_code == 401


def test_create_with_unknown_parent_404(client, auth_headers):
    resp = client.post(
        "/api/categories", json={"name": "x", "parent_id": 999}, headers=auth_headers
    )
    assert resp.status_code == 404


def test_get_category(client, auth_headers):
    created = client.post("/api/categories", json={"name": "shared"}, headers=auth_headers).json()
    resp = client.get(f"/api/categories/{created['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "shared"


def test_get_missing_category_404(client, auth_headers):
    resp = client.get("/api/categories/999", headers=auth_headers)
    assert resp.status_code == 404


def test_create_category_defaults_is_income_false(client, auth_headers):
    resp = client.post("/api/categories", json={"name": "shared"}, headers=auth_headers)
    assert resp.json()["is_income"] is False


def test_create_category_marked_as_income(client, auth_headers):
    resp = client.post("/api/categories", json={"name": "salary", "is_income": True}, headers=auth_headers)
    assert resp.json()["is_income"] is True


def test_update_category_income_flag(client, auth_headers):
    created = client.post("/api/categories", json={"name": "salary"}, headers=auth_headers).json()
    resp = client.patch(
        f"/api/categories/{created['id']}",
        json={"is_income": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_income"] is True


def test_update_category_override_color(client, auth_headers):
    created = client.post("/api/categories", json={"name": "shared"}, headers=auth_headers).json()
    resp = client.patch(
        f"/api/categories/{created['id']}",
        json={"color": "#123456"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["color"] == "#123456"


def test_update_explicit_parent_id(client, auth_headers):
    a = client.post("/api/categories", json={"name": "shared"}, headers=auth_headers).json()
    b = client.post("/api/categories", json={"name": "personal"}, headers=auth_headers).json()
    child = client.post(
        "/api/categories", json={"name": "groceries", "parent_id": a["id"]}, headers=auth_headers
    ).json()

    resp = client.patch(
        f"/api/categories/{child['id']}",
        json={"parent_id": b["id"]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["parent_id"] == b["id"]


def test_update_missing_category_404(client, auth_headers):
    resp = client.patch("/api/categories/999", json={"name": "x"}, headers=auth_headers)
    assert resp.status_code == 404


def test_update_validation_error_returns_422(client, auth_headers):
    a = client.post("/api/categories", json={"name": "shared"}, headers=auth_headers).json()
    resp = client.patch(
        f"/api/categories/{a['id']}",
        json={"parent_id": a["id"]},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_archive_missing_category_404(client, auth_headers):
    resp = client.post("/api/categories/999/archive", headers=auth_headers)
    assert resp.status_code == 404


def test_update_move_to_root(client, auth_headers):
    parent = client.post("/api/categories", json={"name": "shared"}, headers=auth_headers).json()
    child = client.post(
        "/api/categories", json={"name": "groceries", "parent_id": parent["id"]}, headers=auth_headers
    ).json()
    resp = client.patch(
        f"/api/categories/{child['id']}",
        json={"move_to_root": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["parent_id"] is None


def test_archive_category_hides_from_default_listing(client, auth_headers):
    created = client.post("/api/categories", json={"name": "shared"}, headers=auth_headers).json()
    resp = client.post(f"/api/categories/{created['id']}/archive", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["archived_at"] is not None

    resp = client.get("/api/categories", headers=auth_headers)
    assert resp.json() == []

    resp = client.get("/api/categories?include_archived=true", headers=auth_headers)
    assert len(resp.json()) == 1


def test_reorder_categories(client, auth_headers):
    a = client.post("/api/categories", json={"name": "shared"}, headers=auth_headers).json()
    b = client.post("/api/categories", json={"name": "personal"}, headers=auth_headers).json()

    resp = client.post(
        "/api/categories/reorder",
        json={"parent_id": None, "ordered_ids": [b["id"], a["id"]]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert [c["name"] for c in resp.json()] == ["personal", "shared"]


def test_reorder_rejects_bad_id_set(client, auth_headers):
    a = client.post("/api/categories", json={"name": "shared"}, headers=auth_headers).json()
    resp = client.post(
        "/api/categories/reorder",
        json={"parent_id": None, "ordered_ids": [a["id"], 999]},
        headers=auth_headers,
    )
    assert resp.status_code == 422

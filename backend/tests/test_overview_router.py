import pytest


@pytest.fixture()
def category_id(client, auth_headers):
    return client.post("/api/categories", json={"name": "shared"}, headers=auth_headers).json()["id"]


def test_requires_auth(client):
    resp = client.get("/api/overview?year=2026&through_month=1")
    assert resp.status_code == 401


def test_overview_returns_rows(client, auth_headers, category_id):
    resp = client.get("/api/overview?year=2026&through_month=1", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["has_budget"] is False


def test_overview_invalid_through_month_422(client, auth_headers, category_id):
    resp = client.get("/api/overview?year=2026&through_month=13", headers=auth_headers)
    assert resp.status_code == 422

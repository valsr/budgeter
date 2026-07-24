import io

import pytest

QIF_BASIC = b"""!Type:Bank
D07/19/2026
T-88.40
PCostco
^
"""


@pytest.fixture()
def account_id(client, auth_headers):
    resp = client.post(
        "/api/accounts",
        json={"name": "Main checking", "type": "asset", "opening_balance": 1000},
        headers=auth_headers,
    )
    return resp.json()["id"]


def test_requires_auth(client):
    resp = client.get("/api/import")
    assert resp.status_code == 401


def test_import_qif_file(client, auth_headers, account_id):
    resp = client.post(
        "/api/import",
        headers=auth_headers,
        data={"account_id": account_id},
        files={"file": ("test.qif", io.BytesIO(QIF_BASIC), "application/octet-stream")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["filename"] == "test.qif"
    assert body["imported_count"] == 1


def test_import_unknown_account_404(client, auth_headers):
    resp = client.post(
        "/api/import",
        headers=auth_headers,
        data={"account_id": 999},
        files={"file": ("test.qif", io.BytesIO(QIF_BASIC), "application/octet-stream")},
    )
    assert resp.status_code == 404


def test_import_bad_qif_422(client, auth_headers, account_id):
    bad = b"D07/19/2026\nTnot-a-number\nPx\n^\n"
    resp = client.post(
        "/api/import",
        headers=auth_headers,
        data={"account_id": account_id},
        files={"file": ("test.qif", io.BytesIO(bad), "application/octet-stream")},
    )
    assert resp.status_code == 422


def test_list_and_get_import_batches(client, auth_headers, account_id):
    created = client.post(
        "/api/import",
        headers=auth_headers,
        data={"account_id": account_id},
        files={"file": ("test.qif", io.BytesIO(QIF_BASIC), "application/octet-stream")},
    ).json()

    resp = client.get("/api/import", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = client.get(f"/api/import/{created['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_missing_batch_404(client, auth_headers):
    resp = client.get("/api/import/999", headers=auth_headers)
    assert resp.status_code == 404


def test_review_queue_flow(client, auth_headers, account_id):
    client.post(
        "/api/import",
        headers=auth_headers,
        data={"account_id": account_id},
        files={"file": ("first.qif", io.BytesIO(QIF_BASIC), "application/octet-stream")},
    )
    near_match = b"D07/19/2026\nT-88.40\nPCOSTCO WHOLESALE #443\n^\n"
    batch2 = client.post(
        "/api/import",
        headers=auth_headers,
        data={"account_id": account_id},
        files={"file": ("second.qif", io.BytesIO(near_match), "application/octet-stream")},
    ).json()
    assert batch2["needs_review_count"] == 1

    resp = client.get("/api/import/review-queue/items", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1

    resp = client.post(
        f"/api/import/review-queue/{items[0]['id']}/resolve",
        json={"action": "skip"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved_skipped"

    resp = client.get("/api/import/review-queue/items", headers=auth_headers)
    assert resp.json() == []


def test_resolve_review_item_new_action(client, auth_headers, account_id):
    client.post(
        "/api/import",
        headers=auth_headers,
        data={"account_id": account_id},
        files={"file": ("first.qif", io.BytesIO(QIF_BASIC), "application/octet-stream")},
    )
    near_match = b"D07/19/2026\nT-88.40\nPCOSTCO WHOLESALE #443\n^\n"
    client.post(
        "/api/import",
        headers=auth_headers,
        data={"account_id": account_id},
        files={"file": ("second.qif", io.BytesIO(near_match), "application/octet-stream")},
    )
    item = client.get("/api/import/review-queue/items", headers=auth_headers).json()[0]
    resp = client.post(
        f"/api/import/review-queue/{item['id']}/resolve",
        json={"action": "new"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved_new"


def test_resolve_missing_review_item_404(client, auth_headers):
    resp = client.post(
        "/api/import/review-queue/999/resolve", json={"action": "skip"}, headers=auth_headers
    )
    assert resp.status_code == 404


def test_resolve_already_resolved_422(client, auth_headers, account_id):
    client.post(
        "/api/import",
        headers=auth_headers,
        data={"account_id": account_id},
        files={"file": ("first.qif", io.BytesIO(QIF_BASIC), "application/octet-stream")},
    )
    near_match = b"D07/19/2026\nT-88.40\nPCOSTCO WHOLESALE #443\n^\n"
    client.post(
        "/api/import",
        headers=auth_headers,
        data={"account_id": account_id},
        files={"file": ("second.qif", io.BytesIO(near_match), "application/octet-stream")},
    )
    item = client.get("/api/import/review-queue/items", headers=auth_headers).json()[0]
    client.post(
        f"/api/import/review-queue/{item['id']}/resolve", json={"action": "skip"}, headers=auth_headers
    )
    resp = client.post(
        f"/api/import/review-queue/{item['id']}/resolve", json={"action": "skip"}, headers=auth_headers
    )
    assert resp.status_code == 422

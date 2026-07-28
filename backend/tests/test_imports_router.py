import io
import json

import pytest

QIF_BASIC = b"""!Type:Bank
D07/19/2026
T-88.40
PCostco
^
"""

QIF_MULTI_ACCOUNT = b"""!Account
NChecking
TBank
^
!Type:Bank
D07/19/2026
T-88.40
PCostco
^
!Account
NCredit Card
TCCard
^
!Type:CCard
D07/20/2026
T-55.00
PAmazon
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


@pytest.fixture()
def category_id(client, auth_headers):
    return client.post("/api/categories", json={"name": "groceries"}, headers=auth_headers).json()["id"]


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


def test_import_runs_background_categorization_in_its_own_session(
    client, auth_headers, account_id, category_id
):
    """Regression test for the background task's DB session handling
    (docs/requirements.md §2.4): run_categorization_in_background opens its
    own session rather than reusing the request's closed one. This asserts
    on the actual side effect — a persisted suggestion — not just that the
    request succeeds, so it would fail if that session were silently a
    no-op (e.g. pointed at an empty/uninitialized database).
    """
    client.post(
        "/api/rules",
        json={
            "match_type": "all",
            "conditions": [{"field": "name", "operator": "contains", "value": "costco"}],
            "target_category_id": category_id,
        },
        headers=auth_headers,
    )

    resp = client.post(
        "/api/import",
        headers=auth_headers,
        data={"account_id": account_id},
        files={"file": ("test.qif", io.BytesIO(QIF_BASIC), "application/octet-stream")},
    )
    assert resp.status_code == 201

    txns = client.get("/api/transactions", headers=auth_headers).json()["items"]
    assert len(txns) == 1
    assert txns[0]["splits"][0]["suggested_category_id"] == category_id


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


def test_detect_accounts_single_account_file_has_no_sections(client, auth_headers):
    resp = client.post(
        "/api/import/detect-accounts",
        headers=auth_headers,
        files={"file": ("test.qif", io.BytesIO(QIF_BASIC), "application/octet-stream")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_account_sections"] is False
    assert body["accounts"] == []


def test_detect_accounts_multi_account_file(client, auth_headers, account_id):
    # account_id fixture creates an account named "Main checking" — distinct
    # from both parsed names, so both come back unmatched (new).
    resp = client.post(
        "/api/import/detect-accounts",
        headers=auth_headers,
        files={"file": ("test.qif", io.BytesIO(QIF_MULTI_ACCOUNT), "application/octet-stream")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_account_sections"] is True
    assert [a["parsed_name"] for a in body["accounts"]] == ["Checking", "Credit Card"]
    assert [a["transaction_count"] for a in body["accounts"]] == [1, 1]
    assert [a["matched_account_id"] for a in body["accounts"]] == [None, None]
    assert [a["suggested_type"] for a in body["accounts"]] == ["asset", "liability"]


def test_detect_accounts_matches_existing_account_by_name(client, auth_headers):
    client.post("/api/accounts", json={"name": "Checking", "type": "asset"}, headers=auth_headers)
    resp = client.post(
        "/api/import/detect-accounts",
        headers=auth_headers,
        files={"file": ("test.qif", io.BytesIO(QIF_MULTI_ACCOUNT), "application/octet-stream")},
    )
    body = resp.json()
    checking = next(a for a in body["accounts"] if a["parsed_name"] == "Checking")
    assert checking["matched_account_id"] is not None


def test_commit_import_creates_new_accounts_and_imports(client, auth_headers):
    resp = client.post(
        "/api/import/commit",
        headers=auth_headers,
        data={
            "resolutions": json.dumps(
                {
                    "resolutions": [
                        {
                            "parsed_name": "Checking",
                            "new_account": {"name": "My Checking", "type": "asset", "opening_balance": 500},
                        },
                        {
                            "parsed_name": "Credit Card",
                            "new_account": {"name": "My Credit Card", "type": "liability"},
                        },
                    ]
                }
            )
        },
        files={"file": ("test.qif", io.BytesIO(QIF_MULTI_ACCOUNT), "application/octet-stream")},
    )
    assert resp.status_code == 201
    batches = resp.json()
    assert len(batches) == 2
    assert {b["imported_count"] for b in batches} == {1}

    accounts = client.get("/api/accounts", headers=auth_headers).json()
    names = {a["name"] for a in accounts}
    assert {"My Checking", "My Credit Card"} <= names


def test_commit_import_maps_to_existing_account(client, auth_headers, account_id):
    resp = client.post(
        "/api/import/commit",
        headers=auth_headers,
        data={
            "resolutions": json.dumps(
                {
                    "resolutions": [
                        {"parsed_name": "Checking", "account_id": account_id},
                        {
                            "parsed_name": "Credit Card",
                            "new_account": {"name": "New CC", "type": "liability"},
                        },
                    ]
                }
            )
        },
        files={"file": ("test.qif", io.BytesIO(QIF_MULTI_ACCOUNT), "application/octet-stream")},
    )
    assert resp.status_code == 201
    batches = {b["account_id"]: b for b in resp.json()}
    assert account_id in batches

    txns = client.get(f"/api/transactions?account_id={account_id}", headers=auth_headers).json()["items"]
    assert len(txns) == 1
    assert txns[0]["name"] == "Costco"


def test_commit_import_missing_resolution_422(client, auth_headers):
    resp = client.post(
        "/api/import/commit",
        headers=auth_headers,
        data={"resolutions": json.dumps({"resolutions": [{"parsed_name": "Checking", "account_id": 999}]})},
        files={"file": ("test.qif", io.BytesIO(QIF_MULTI_ACCOUNT), "application/octet-stream")},
    )
    # "Credit Card" block has no resolution entry at all.
    assert resp.status_code == 422


def test_commit_import_unresolvable_account_404(client, auth_headers):
    resp = client.post(
        "/api/import/commit",
        headers=auth_headers,
        data={
            "resolutions": json.dumps(
                {
                    "resolutions": [
                        {"parsed_name": "Checking", "account_id": 999},
                        {"parsed_name": "Credit Card", "account_id": 999},
                    ]
                }
            )
        },
        files={"file": ("test.qif", io.BytesIO(QIF_MULTI_ACCOUNT), "application/octet-stream")},
    )
    assert resp.status_code == 404


def test_commit_import_resolution_missing_target_422(client, auth_headers):
    resp = client.post(
        "/api/import/commit",
        headers=auth_headers,
        data={"resolutions": json.dumps({"resolutions": [{"parsed_name": None}]})},
        files={"file": ("test.qif", io.BytesIO(QIF_BASIC), "application/octet-stream")},
    )
    assert resp.status_code == 422


def test_detect_accounts_qfx_file(client, auth_headers):
    qfx = b"""<OFX>
<BANKMSGSRSV1>
<STMTTRNRS>
<STMTRS>
<BANKACCTFROM>
<ACCTID>1234567890
<ACCTTYPE>CHECKING
</BANKACCTFROM>
<BANKTRANLIST>
<STMTTRN>
<DTPOSTED>20260719
<TRNAMT>-88.40
<NAME>COSTCO
</STMTTRN>
</BANKTRANLIST>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>
"""
    resp = client.post(
        "/api/import/detect-accounts",
        headers=auth_headers,
        files={"file": ("test.qfx", io.BytesIO(qfx), "application/octet-stream")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_account_sections"] is True
    assert body["accounts"] == [
        {
            "parsed_name": "1234567890",
            "transaction_count": 1,
            "matched_account_id": None,
            "suggested_type": "asset",
        }
    ]


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

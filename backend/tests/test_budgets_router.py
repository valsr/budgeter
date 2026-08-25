import pytest


@pytest.fixture()
def account_id(client, auth_headers):
    return client.post(
        "/api/accounts", json={"name": "Main", "type": "asset", "opening_balance": 1000}, headers=auth_headers
    ).json()["id"]


@pytest.fixture()
def shared_id(client, auth_headers):
    return client.post("/api/categories", json={"name": "shared"}, headers=auth_headers).json()["id"]


@pytest.fixture()
def groceries_id(client, auth_headers, shared_id):
    return client.post(
        "/api/categories", json={"name": "groceries", "parent_id": shared_id}, headers=auth_headers
    ).json()["id"]


def test_requires_auth(client):
    resp = client.get("/api/budgets")
    assert resp.status_code == 401


def test_create_and_list_budgets(client, auth_headers, groceries_id):
    resp = client.post(
        "/api/budgets",
        json={"name": "Household", "year": 2026, "categories": [{"category_id": groceries_id, "monthly_amounts": {"1": 400}}]},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    budget = resp.json()
    assert budget["name"] == "Household"

    resp = client.get("/api/budgets", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_create_budget_drops_non_leaf_category(client, auth_headers, shared_id, groceries_id):
    resp = client.post(
        "/api/budgets",
        json={"name": "Bad", "year": 2026, "categories": [{"category_id": shared_id, "monthly_amounts": {"1": 100}}]},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["budget_categories"] == []
    assert body["dropped_categories"] == [
        {"category_id": shared_id, "name": "shared", "reason": "broken_down", "account_id": None}
    ]


def test_create_budget_drops_unknown_category(client, auth_headers):
    resp = client.post(
        "/api/budgets",
        json={"name": "x", "year": 2026, "categories": [{"category_id": 999, "monthly_amounts": {"1": 100}}]},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["dropped_categories"] == [
        {"category_id": 999, "name": None, "reason": "removed", "account_id": None}
    ]


def test_get_budget(client, auth_headers, groceries_id):
    created = client.post(
        "/api/budgets",
        json={"name": "Household", "year": 2026, "categories": [{"category_id": groceries_id, "monthly_amounts": {"1": 400}}]},
        headers=auth_headers,
    ).json()
    resp = client.get(f"/api/budgets/{created['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Household"


def test_get_missing_budget_404(client, auth_headers):
    resp = client.get("/api/budgets/999", headers=auth_headers)
    assert resp.status_code == 404


def test_update_budget(client, auth_headers, groceries_id):
    created = client.post(
        "/api/budgets",
        json={"name": "Household", "year": 2026, "categories": [{"category_id": groceries_id, "monthly_amounts": {"1": 400}}]},
        headers=auth_headers,
    ).json()
    resp = client.patch(f"/api/budgets/{created['id']}", json={"name": "Renamed"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"


def test_update_budget_keeping_same_category_selected(client, auth_headers, groceries_id):
    """Regression guard: editing a budget without changing which categories
    are selected (the common case -- only amounts change) used to raise a
    UNIQUE constraint IntegrityError, because the old (budget_id,
    category_id) row wasn't flushed as deleted before the replacement row
    for the same category was inserted."""
    created = client.post(
        "/api/budgets",
        json={"name": "Household", "year": 2026, "categories": [{"category_id": groceries_id, "monthly_amounts": {"1": 400}}]},
        headers=auth_headers,
    ).json()
    resp = client.patch(
        f"/api/budgets/{created['id']}",
        json={"year": 2026, "categories": [{"category_id": groceries_id, "monthly_amounts": {"1": 500}}]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["budget_categories"][0]["amounts"][0]["amount"] == 500.0


def test_update_missing_budget_404(client, auth_headers):
    resp = client.patch("/api/budgets/999", json={"name": "x"}, headers=auth_headers)
    assert resp.status_code == 404


def test_update_budget_drops_a_category_that_was_broken_down(client, auth_headers, groceries_id, shared_id):
    """The reported bug: saving an existing budget whose category has since
    gained children used to 422 with no way out, because the editor renders a
    broken-down category as an unselectable section header."""
    created = client.post(
        "/api/budgets",
        json={"name": "Household", "year": 2026, "categories": [{"category_id": groceries_id, "monthly_amounts": {"1": 400}}]},
        headers=auth_headers,
    ).json()
    client.post(
        "/api/categories", json={"name": "alcohol", "parent_id": groceries_id}, headers=auth_headers
    )

    resp = client.patch(
        f"/api/budgets/{created['id']}",
        json={"year": 2026, "categories": [{"category_id": groceries_id, "monthly_amounts": {"1": 400}}]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["budget_categories"] == []
    assert body["dropped_categories"] == [
        {"category_id": groceries_id, "name": "groceries", "reason": "broken_down", "account_id": None}
    ]


def test_read_endpoints_report_no_dropped_categories(client, auth_headers, groceries_id):
    created = client.post(
        "/api/budgets",
        json={"name": "Household", "year": 2026, "categories": [{"category_id": groceries_id, "monthly_amounts": {"1": 400}}]},
        headers=auth_headers,
    ).json()
    assert created["dropped_categories"] == []
    resp = client.get(f"/api/budgets/{created['id']}", headers=auth_headers)
    assert resp.json()["dropped_categories"] == []


def test_delete_budget(client, auth_headers, groceries_id):
    created = client.post(
        "/api/budgets",
        json={"name": "Household", "year": 2026, "categories": [{"category_id": groceries_id, "monthly_amounts": {"1": 400}}]},
        headers=auth_headers,
    ).json()
    resp = client.delete(f"/api/budgets/{created['id']}", headers=auth_headers)
    assert resp.status_code == 204
    assert client.get(f"/api/budgets/{created['id']}", headers=auth_headers).status_code == 404


def test_delete_missing_budget_404(client, auth_headers):
    resp = client.delete("/api/budgets/999", headers=auth_headers)
    assert resp.status_code == 404


def test_get_report(client, auth_headers, account_id, shared_id, groceries_id):
    created = client.post(
        "/api/budgets",
        json={
            "name": "Household",
            "year": 2026,
            "categories": [{"category_id": groceries_id, "monthly_amounts": {"1": 400, "2": 400}}],
        },
        headers=auth_headers,
    ).json()
    client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-05", "name": "Costco", "splits": [{"category_id": groceries_id, "amount": -380.0}]},
        headers=auth_headers,
    )

    resp = client.get(f"/api/budgets/{created['id']}/report?year=2026&through_month=2", headers=auth_headers)
    assert resp.status_code == 200
    rows = resp.json()
    by_name = {r["name"]: r for r in rows}
    assert by_name["shared"]["is_parent"] is True
    assert by_name["shared"]["monthly"]["1"] == {"budgeted": 400.0, "actual": 380.0}
    assert by_name["groceries"]["ytd_diff"] == pytest.approx(420.0)  # (400+400)-(380+0)


def test_get_report_missing_budget_404(client, auth_headers):
    resp = client.get("/api/budgets/999/report?year=2026&through_month=1", headers=auth_headers)
    assert resp.status_code == 404


def test_get_report_invalid_through_month_422(client, auth_headers, groceries_id):
    created = client.post(
        "/api/budgets",
        json={"name": "Household", "year": 2026, "categories": [{"category_id": groceries_id, "monthly_amounts": {"1": 400}}]},
        headers=auth_headers,
    ).json()
    resp = client.get(f"/api/budgets/{created['id']}/report?year=2026&through_month=13", headers=auth_headers)
    assert resp.status_code == 422


def test_report_accepts_repeated_account_id_filters(client, auth_headers, groceries_id, account_id):
    created = client.post(
        "/api/budgets",
        json={"name": "Household", "year": 2026, "categories": [{"category_id": groceries_id, "monthly_amounts": {"1": 400}}]},
        headers=auth_headers,
    ).json()
    other = client.post(
        "/api/accounts", json={"name": "Visa", "type": "liability", "opening_balance": 0}, headers=auth_headers
    ).json()["id"]
    for account, amount in ((account_id, -240.0), (other, -140.0)):
        client.post(
            "/api/transactions",
            json={
                "account_id": account,
                "date": "2026-01-05",
                "name": "shop",
                "splits": [{"category_id": groceries_id, "amount": amount}],
            },
            headers=auth_headers,
        )

    url = f"/api/budgets/{created['id']}/report?year=2026&through_month=1"
    unfiltered = client.get(url, headers=auth_headers).json()
    assert next(r for r in unfiltered if r["name"] == "groceries")["monthly"]["1"]["actual"] == 380.0

    filtered = client.get(f"{url}&account_id={account_id}", headers=auth_headers).json()
    row = next(r for r in filtered if r["name"] == "groceries")
    assert row["monthly"]["1"]["actual"] == 240.0
    # A whole-category plan has no attributable share while filtered.
    assert row["has_budget"] is False

    both = client.get(f"{url}&account_id={account_id}&account_id={other}", headers=auth_headers).json()
    assert next(r for r in both if r["name"] == "groceries")["monthly"]["1"]["actual"] == 380.0

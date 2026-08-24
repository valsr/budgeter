import pytest


@pytest.fixture()
def category_id(client, auth_headers):
    return client.post("/api/categories", json={"name": "personal"}, headers=auth_headers).json()["id"]


@pytest.fixture()
def account_id(client, auth_headers):
    return client.post(
        "/api/accounts", json={"name": "Main", "type": "asset", "opening_balance": 1000}, headers=auth_headers
    ).json()["id"]


def test_requires_auth(client):
    resp = client.get("/api/rules")
    assert resp.status_code == 401


def _rule_payload(category_id, value="github"):
    return {
        "match_type": "all",
        "conditions": [{"field": "name", "operator": "contains", "value": value}],
        "target_category_id": category_id,
    }


def test_create_and_list_rules(client, auth_headers, category_id):
    resp = client.post("/api/rules", json=_rule_payload(category_id), headers=auth_headers)
    assert resp.status_code == 201
    rule = resp.json()
    assert rule["priority"] == 0

    resp = client.get("/api/rules", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_create_rule_unknown_category_404(client, auth_headers):
    resp = client.post("/api/rules", json=_rule_payload(999), headers=auth_headers)
    assert resp.status_code == 404


def test_create_rule_no_conditions_422(client, auth_headers, category_id):
    payload = _rule_payload(category_id)
    payload["conditions"] = []
    resp = client.post("/api/rules", json=payload, headers=auth_headers)
    assert resp.status_code == 422


def test_create_rule_triggers_categorization(client, auth_headers, category_id, account_id):
    txn = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "GitHub Inc.", "splits": [{"amount": -21.0}]},
        headers=auth_headers,
    ).json()

    client.post("/api/rules", json=_rule_payload(category_id), headers=auth_headers)

    refreshed = client.get(f"/api/transactions/{txn['id']}", headers=auth_headers).json()
    assert refreshed["splits"][0]["suggested_category_id"] == category_id


def test_get_rule(client, auth_headers, category_id):
    created = client.post("/api/rules", json=_rule_payload(category_id), headers=auth_headers).json()
    resp = client.get(f"/api/rules/{created['id']}", headers=auth_headers)
    assert resp.status_code == 200


def test_get_missing_rule_404(client, auth_headers):
    resp = client.get("/api/rules/999", headers=auth_headers)
    assert resp.status_code == 404


def test_update_rule(client, auth_headers, category_id):
    created = client.post("/api/rules", json=_rule_payload(category_id), headers=auth_headers).json()
    resp = client.patch(
        f"/api/rules/{created['id']}",
        json={"conditions": [{"field": "name", "operator": "contains", "value": "spotify"}]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["conditions"][0]["value"] == "spotify"


def test_update_missing_rule_404(client, auth_headers):
    resp = client.patch("/api/rules/999", json={"match_type": "any"}, headers=auth_headers)
    assert resp.status_code == 404


def test_update_rule_bad_conditions_422(client, auth_headers, category_id):
    created = client.post("/api/rules", json=_rule_payload(category_id), headers=auth_headers).json()
    resp = client.patch(f"/api/rules/{created['id']}", json={"conditions": []}, headers=auth_headers)
    assert resp.status_code == 422


def test_delete_rule(client, auth_headers, category_id):
    created = client.post("/api/rules", json=_rule_payload(category_id), headers=auth_headers).json()
    resp = client.delete(f"/api/rules/{created['id']}", headers=auth_headers)
    assert resp.status_code == 204
    assert client.get(f"/api/rules/{created['id']}", headers=auth_headers).status_code == 404


def test_delete_missing_rule_404(client, auth_headers):
    resp = client.delete("/api/rules/999", headers=auth_headers)
    assert resp.status_code == 404


def test_reorder_rules(client, auth_headers, category_id):
    r1 = client.post("/api/rules", json=_rule_payload(category_id, "a"), headers=auth_headers).json()
    r2 = client.post("/api/rules", json=_rule_payload(category_id, "b"), headers=auth_headers).json()
    resp = client.post(
        "/api/rules/reorder", json={"ordered_ids": [r2["id"], r1["id"]]}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert [r["id"] for r in resp.json()] == [r2["id"], r1["id"]]


def test_reorder_rejects_bad_id_set(client, auth_headers, category_id):
    r1 = client.post("/api/rules", json=_rule_payload(category_id), headers=auth_headers).json()
    resp = client.post("/api/rules/reorder", json={"ordered_ids": [r1["id"], 999]}, headers=auth_headers)
    assert resp.status_code == 422


def _categorized_txn(client, auth_headers, account_id, name, category_id, amount=-10.0, date="2026-01-01"):
    return client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": date, "name": name, "splits": [{"category_id": category_id, "amount": amount}]},
        headers=auth_headers,
    ).json()


def test_learn_check_covered_when_existing_rule_matches_same_category(client, auth_headers, category_id, account_id):
    client.post("/api/rules", json=_rule_payload(category_id, "github"), headers=auth_headers)
    txn = _categorized_txn(client, auth_headers, account_id, "GitHub Inc.", category_id)
    resp = client.post("/api/rules/learn-check", json={"transaction_id": txn["id"]}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"status": "covered", "conflict": None, "suggestion": None}


def test_learn_check_conflict_when_existing_rule_matches_different_category(
    client, auth_headers, category_id, account_id
):
    other = client.post("/api/categories", json={"name": "other"}, headers=auth_headers).json()["id"]
    rule = client.post("/api/rules", json=_rule_payload(category_id, "github"), headers=auth_headers).json()
    txn = _categorized_txn(client, auth_headers, account_id, "GitHub Inc.", other)

    resp = client.post("/api/rules/learn-check", json={"transaction_id": txn["id"]}, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "conflict"
    assert body["conflict"]["rule_id"] == rule["id"]
    assert body["conflict"]["matched_category_id"] == category_id
    assert body["conflict"]["assigned_category_id"] == other
    # regression guard: str-mixin enums must render their plain value, not
    # "ConditionField.NAME" (Python 3.11+ changed Enum.__format__ defaults)
    assert body["conflict"]["rule_summary"] == "name contains 'github'"

    # nothing auto-reverted
    refreshed = client.get(f"/api/transactions/{txn['id']}", headers=auth_headers).json()
    assert refreshed["splits"][0]["category_id"] == other


def test_learn_check_conflict_summary_names_the_account(client, auth_headers, category_id, account_id):
    other = client.post("/api/categories", json={"name": "other"}, headers=auth_headers).json()["id"]
    client.post(
        "/api/rules",
        json={
            "match_type": "all",
            "conditions": [{"field": "account", "operator": "in", "value": str(account_id)}],
            "target_category_id": category_id,
        },
        headers=auth_headers,
    )
    txn = _categorized_txn(client, auth_headers, account_id, "GitHub Inc.", other)

    resp = client.post("/api/rules/learn-check", json={"transaction_id": txn["id"]}, headers=auth_headers)
    body = resp.json()
    assert body["status"] == "conflict"
    # An account condition stores ids; the summary must read as names.
    assert body["conflict"]["rule_summary"] == "account in 'Main'"


def test_learn_check_suggestion_tier1_happy_path(client, auth_headers, category_id, account_id):
    for i, suffix in enumerate(["775", "756", "123"]):
        _categorized_txn(
            client, auth_headers, account_id, f"McDonalds #{suffix}", category_id, date=f"2026-01-0{i + 1}"
        )
    newest = _categorized_txn(client, auth_headers, account_id, "McDonalds #999", category_id, date="2026-01-10")

    resp = client.post("/api/rules/learn-check", json={"transaction_id": newest["id"]}, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "suggestion"
    assert body["suggestion"]["tier"] == 1
    assert body["suggestion"]["target_category_id"] == category_id
    assert body["suggestion"]["conditions"] == [{"field": "name", "operator": "contains", "value": "mcdonalds"}]


def test_learn_check_none_when_too_few_candidates(client, auth_headers, category_id, account_id):
    txn = _categorized_txn(client, auth_headers, account_id, "McDonalds #1", category_id)
    resp = client.post("/api/rules/learn-check", json={"transaction_id": txn["id"]}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "none"


def test_learn_check_counts_the_just_categorized_transaction_toward_the_threshold(
    client, auth_headers, category_id, account_id
):
    # Only 2 *other* prior categorizations exist -- the transaction just
    # categorized (checked below) is the 3rd data point, not a 4th on top of
    # an already-satisfied 3. The sample-size bar is "does this category
    # have 3 transactions total to learn from," not "3 besides this one."
    for i, suffix in enumerate(["775", "756"]):
        _categorized_txn(client, auth_headers, account_id, f"McDonalds #{suffix}", category_id, date=f"2026-01-0{i + 1}")
    newest = _categorized_txn(client, auth_headers, account_id, "McDonalds #999", category_id, date="2026-01-10")

    resp = client.post("/api/rules/learn-check", json={"transaction_id": newest["id"]}, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "suggestion"
    assert body["suggestion"]["tier"] == 1


def test_learn_check_none_for_uncategorized_transaction(client, auth_headers, account_id):
    txn = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "x", "splits": [{"amount": -1.0}]},
        headers=auth_headers,
    ).json()
    resp = client.post("/api/rules/learn-check", json={"transaction_id": txn["id"]}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "none"


def test_learn_check_missing_transaction_404(client, auth_headers):
    resp = client.post("/api/rules/learn-check", json={"transaction_id": 999}, headers=auth_headers)
    assert resp.status_code == 404


def test_preview_matches_counts_uncategorized_and_excludes_categorized(client, auth_headers, category_id, account_id):
    client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "McDonalds #1", "splits": [{"amount": -5.0}]},
        headers=auth_headers,
    )
    client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-02", "name": "Starbucks", "splits": [{"amount": -5.0}]},
        headers=auth_headers,
    )
    _categorized_txn(client, auth_headers, account_id, "McDonalds #2", category_id)  # already categorized, excluded

    resp = client.post(
        "/api/rules/preview-matches",
        json={
            "match_type": "all",
            "conditions": [{"field": "name", "operator": "contains", "value": "mcdonalds"}],
            "target_category_id": category_id,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["matches"][0]["name"] == "McDonalds #1"


def test_learn_endpoint_creates_rule_and_backfills_matches(client, auth_headers, category_id, account_id):
    matching = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "McDonalds #1", "splits": [{"amount": -5.0}]},
        headers=auth_headers,
    ).json()
    non_matching = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-02", "name": "Starbucks", "splits": [{"amount": -5.0}]},
        headers=auth_headers,
    ).json()

    resp = client.post(
        "/api/rules/learn",
        json={
            "match_type": "all",
            "conditions": [{"field": "name", "operator": "contains", "value": "mcdonalds"}],
            "target_category_id": category_id,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["rule"]["target_category_id"] == category_id
    assert body["confirmed_count"] == 1
    assert body["confirmed_transaction_ids"] == [matching["id"]]

    # regression: appears in the rule list like any other rule
    assert any(r["id"] == body["rule"]["id"] for r in client.get("/api/rules", headers=auth_headers).json())

    refreshed_match = client.get(f"/api/transactions/{matching['id']}", headers=auth_headers).json()
    assert refreshed_match["splits"][0]["category_id"] == category_id  # directly confirmed, not just suggested

    refreshed_non_match = client.get(f"/api/transactions/{non_matching['id']}", headers=auth_headers).json()
    assert refreshed_non_match["splits"][0]["category_id"] is None


def test_learn_endpoint_unknown_category_404(client, auth_headers):
    resp = client.post(
        "/api/rules/learn",
        json={
            "match_type": "all",
            "conditions": [{"field": "name", "operator": "contains", "value": "mcdonalds"}],
            "target_category_id": 999,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_learn_endpoint_no_conditions_422(client, auth_headers, category_id):
    resp = client.post(
        "/api/rules/learn",
        json={"match_type": "all", "conditions": [], "target_category_id": category_id},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_plain_create_rule_never_sets_category_id_directly(client, auth_headers, category_id, account_id):
    """Regression guard: plain POST /api/rules must stay suggest-only --
    only POST /api/rules/learn does the one-time auto-confirm backfill."""
    txn = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "McDonalds #1", "splits": [{"amount": -5.0}]},
        headers=auth_headers,
    ).json()
    client.post("/api/rules", json=_rule_payload(category_id, "mcdonalds"), headers=auth_headers)

    refreshed = client.get(f"/api/transactions/{txn['id']}", headers=auth_headers).json()
    assert refreshed["splits"][0]["category_id"] is None
    assert refreshed["splits"][0]["suggested_category_id"] == category_id


def test_recategorize_endpoint(client, auth_headers, category_id, account_id):
    txn = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "GitHub Inc.", "splits": [{"amount": -21.0}]},
        headers=auth_headers,
    ).json()
    client.post("/api/rules", json=_rule_payload(category_id), headers=auth_headers)
    resp = client.post("/api/rules/recategorize", json={"transaction_ids": [txn["id"]]}, headers=auth_headers)
    assert resp.status_code == 200
    # matches the rule again (idempotent re-suggest of the same category, not a "new" count)
    assert resp.json() == {"suggested_count": 1}


def test_run_preview_lists_matches_without_persisting(client, auth_headers, category_id, account_id):
    matching = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "GitHub Inc.", "splits": [{"amount": -21.0}]},
        headers=auth_headers,
    ).json()
    client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-02", "name": "Starbucks", "splits": [{"amount": -5.0}]},
        headers=auth_headers,
    )
    _categorized_txn(client, auth_headers, account_id, "GitHub Inc. #2", category_id)  # already categorized, excluded

    client.post("/api/rules", json=_rule_payload(category_id), headers=auth_headers)

    # rule creation itself already suggested a category (see
    # test_create_rule_triggers_categorization) -- clear it so we can prove
    # run-preview alone doesn't set it again
    refreshed = client.get(f"/api/transactions/{matching['id']}", headers=auth_headers).json()
    split_id = refreshed["splits"][0]["id"]
    client.post(f"/api/transactions/{matching['id']}/splits/{split_id}/reject-suggestion", headers=auth_headers)

    resp = client.get("/api/rules/run-preview", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0] == {
        "transaction_id": matching["id"],
        "date": "2026-01-01",
        "name": "GitHub Inc.",
        "account_id": account_id,
        "category_id": category_id,
        "amount": -21.0,
    }

    # a dry run -- nothing persisted
    refreshed = client.get(f"/api/transactions/{matching['id']}", headers=auth_headers).json()
    assert refreshed["splits"][0]["suggested_category_id"] is None


def test_run_preview_empty_when_no_rules(client, auth_headers, account_id):
    client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "GitHub Inc.", "splits": [{"amount": -21.0}]},
        headers=auth_headers,
    )
    resp = client.get("/api/rules/run-preview", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_accept_and_reject_suggestion_endpoints(client, auth_headers, category_id, account_id):
    txn = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "GitHub Inc.", "splits": [{"amount": -21.0}]},
        headers=auth_headers,
    ).json()
    client.post("/api/rules", json=_rule_payload(category_id), headers=auth_headers)
    refreshed = client.get(f"/api/transactions/{txn['id']}", headers=auth_headers).json()
    split_id = refreshed["splits"][0]["id"]

    resp = client.post(
        f"/api/transactions/{txn['id']}/splits/{split_id}/accept-suggestion", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["category_id"] == category_id


def test_reject_suggestion_endpoint(client, auth_headers, category_id, account_id):
    txn = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "GitHub Inc.", "splits": [{"amount": -21.0}]},
        headers=auth_headers,
    ).json()
    client.post("/api/rules", json=_rule_payload(category_id), headers=auth_headers)
    refreshed = client.get(f"/api/transactions/{txn['id']}", headers=auth_headers).json()
    split_id = refreshed["splits"][0]["id"]

    resp = client.post(
        f"/api/transactions/{txn['id']}/splits/{split_id}/reject-suggestion", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["category_id"] is None
    assert resp.json()["suggested_category_id"] is None


def test_accept_suggestion_missing_split_404(client, auth_headers, account_id):
    txn = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "x", "splits": [{"amount": -1.0}]},
        headers=auth_headers,
    ).json()
    resp = client.post(f"/api/transactions/{txn['id']}/splits/999/accept-suggestion", headers=auth_headers)
    assert resp.status_code == 404


def test_accept_suggestion_no_pending_422(client, auth_headers, account_id):
    txn = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "x", "splits": [{"amount": -1.0}]},
        headers=auth_headers,
    ).json()
    split_id = txn["splits"][0]["id"]
    resp = client.post(f"/api/transactions/{txn['id']}/splits/{split_id}/accept-suggestion", headers=auth_headers)
    assert resp.status_code == 422


def test_reject_suggestion_missing_split_404(client, auth_headers, account_id):
    txn = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "x", "splits": [{"amount": -1.0}]},
        headers=auth_headers,
    ).json()
    resp = client.post(f"/api/transactions/{txn['id']}/splits/999/reject-suggestion", headers=auth_headers)
    assert resp.status_code == 404


def test_reject_suggestion_no_pending_422(client, auth_headers, account_id):
    txn = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-01-01", "name": "x", "splits": [{"amount": -1.0}]},
        headers=auth_headers,
    ).json()
    split_id = txn["splits"][0]["id"]
    resp = client.post(f"/api/transactions/{txn['id']}/splits/{split_id}/reject-suggestion", headers=auth_headers)
    assert resp.status_code == 422


# --- account conditions match by set membership ------------------------


@pytest.fixture()
def second_account_id(client, auth_headers):
    return client.post(
        "/api/accounts", json={"name": "Home", "type": "asset", "opening_balance": 0}, headers=auth_headers
    ).json()["id"]


def _account_rule(client, auth_headers, category_id, operator, account_ids):
    return client.post(
        "/api/rules",
        json={
            "match_type": "all",
            "conditions": [
                {
                    "field": "account",
                    "operator": operator,
                    "value": ",".join(str(i) for i in account_ids),
                }
            ],
            "target_category_id": category_id,
        },
        headers=auth_headers,
    )


def test_create_rule_with_multi_account_condition(
    client, auth_headers, category_id, account_id, second_account_id
):
    resp = _account_rule(client, auth_headers, category_id, "in", [account_id, second_account_id])
    assert resp.status_code == 201
    assert resp.json()["conditions"][0]["value"] == f"{account_id},{second_account_id}"


def test_create_rule_account_equals_rejected(client, auth_headers, category_id, account_id):
    resp = _account_rule(client, auth_headers, category_id, "equals", [account_id])
    assert resp.status_code == 422


def test_preview_matches_account_in_covers_every_listed_account(
    client, auth_headers, category_id, account_id, second_account_id
):
    for account in (account_id, second_account_id):
        client.post(
            "/api/transactions",
            json={
                "account_id": account,
                "date": "2026-01-01",
                "name": "Anything",
                "splits": [{"amount": -10.0}],
            },
            headers=auth_headers,
        )

    resp = client.post(
        "/api/rules/preview-matches",
        json={
            "match_type": "all",
            "conditions": [
                {"field": "account", "operator": "in", "value": f"{account_id},{second_account_id}"}
            ],
            "target_category_id": category_id,
        },
        headers=auth_headers,
    )
    assert resp.json()["count"] == 2


def test_preview_matches_account_not_in_excludes_listed_accounts(
    client, auth_headers, category_id, account_id, second_account_id
):
    for account in (account_id, second_account_id):
        client.post(
            "/api/transactions",
            json={
                "account_id": account,
                "date": "2026-01-01",
                "name": "Anything",
                "splits": [{"amount": -10.0}],
            },
            headers=auth_headers,
        )

    resp = client.post(
        "/api/rules/preview-matches",
        json={
            "match_type": "all",
            "conditions": [{"field": "account", "operator": "not_in", "value": str(account_id)}],
            "target_category_id": category_id,
        },
        headers=auth_headers,
    )
    body = resp.json()
    assert body["count"] == 1


def test_conflict_summary_names_every_account_in_the_set(
    client, auth_headers, category_id, account_id, second_account_id
):
    other = client.post("/api/categories", json={"name": "other"}, headers=auth_headers).json()["id"]
    _account_rule(client, auth_headers, category_id, "in", [account_id, second_account_id])
    txn = _categorized_txn(client, auth_headers, account_id, "GitHub Inc.", other)

    resp = client.post("/api/rules/learn-check", json={"transaction_id": txn["id"]}, headers=auth_headers)
    assert resp.json()["conflict"]["rule_summary"] == "account in 'Main, Home'"

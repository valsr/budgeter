import datetime as dt

import pytest

from app.models.account import AccountType
from app.models.rule import ConditionField, ConditionOperator, MatchType
from app.services import accounts as accounts_svc
from app.services import categories as categories_svc
from app.services import rules as rules_svc
from app.services import transactions as txn_svc


@pytest.fixture()
def account(db_session):
    return accounts_svc.create_account(
        db_session, name="Main", type=AccountType.ASSET, opening_balance=1000
    )


@pytest.fixture()
def category(db_session):
    return categories_svc.create_category(db_session, "personal")


def _categorize(db_session, account, category, name, day):
    txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, day), name, [(category.id, -10.0)]
    )


def test_suggests_rule_after_threshold_repetitions(db_session, account, category):
    for day in (1, 2, 3):
        _categorize(db_session, account, category, "GITHUB INC", day)

    suggestions = rules_svc.suggest_new_rules(db_session, threshold=3)
    assert len(suggestions) == 1
    s = suggestions[0]
    assert s["target_category_id"] == category.id
    assert s["occurrence_count"] == 3
    assert s["conditions"][0]["value"] == "github inc"
    assert s["match_type"] == MatchType.ALL


def test_no_suggestion_below_threshold(db_session, account, category):
    for day in (1, 2):
        _categorize(db_session, account, category, "GITHUB INC", day)

    suggestions = rules_svc.suggest_new_rules(db_session, threshold=3)
    assert suggestions == []


def test_suggestions_ignore_uncategorized_transactions(db_session, account):
    for day in (1, 2, 3):
        txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, day), "Amazon", [(None, -10.0)]
        )
    assert rules_svc.suggest_new_rules(db_session, threshold=3) == []


def test_suggestions_ignore_transfers(db_session, account):
    other = accounts_svc.create_account(
        db_session, name="Card", type=AccountType.LIABILITY, opening_balance=0
    )
    for _ in range(3):
        txn_svc.create_transfer(db_session, account.id, other.id, dt.date(2026, 1, 1), "Payment", 10.0)
    assert rules_svc.suggest_new_rules(db_session, threshold=3) == []


def test_suggestion_normalizes_names_across_variants(db_session, account, category):
    _categorize(db_session, account, category, "SPOTIFY *19.99", 1)
    _categorize(db_session, account, category, "Spotify  19.99", 2)
    _categorize(db_session, account, category, "spotify 19.99!!", 3)

    suggestions = rules_svc.suggest_new_rules(db_session, threshold=3)
    assert len(suggestions) == 1
    assert suggestions[0]["occurrence_count"] == 3


def test_existing_matching_rule_suppresses_suggestion(db_session, account, category):
    for day in (1, 2, 3):
        _categorize(db_session, account, category, "GITHUB INC", day)

    rules_svc.create_rule(
        db_session,
        MatchType.ALL,
        [(ConditionField.NAME, ConditionOperator.CONTAINS, "github inc")],
        category.id,
    )

    assert rules_svc.suggest_new_rules(db_session, threshold=3) == []


def test_suggestions_sorted_by_occurrence_count_desc(db_session, account, category):
    other_category = categories_svc.create_category(db_session, "shared")
    for day in (1, 2, 3, 4):
        _categorize(db_session, account, category, "GITHUB INC", day)
    for day in (5, 6, 7):
        _categorize(db_session, account, other_category, "SPOTIFY", day)

    suggestions = rules_svc.suggest_new_rules(db_session, threshold=3)
    assert len(suggestions) == 2
    assert suggestions[0]["occurrence_count"] == 4
    assert suggestions[1]["occurrence_count"] == 3

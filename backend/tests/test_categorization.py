import datetime as dt

import pytest

from app.models.account import AccountType
from app.models.rule import ConditionField, ConditionOperator, MatchType
from app.models.split import SuggestionSource
from app.services import accounts as accounts_svc
from app.services import categories as categories_svc
from app.services import categorization
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


def test_no_rules_means_no_suggestions(db_session, account):
    txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 1), "GitHub", [(None, -21.0)])
    count = categorization.run_categorization(db_session)
    assert count == 0


def test_matching_rule_suggests_category(db_session, account, category):
    rules_svc.create_rule(
        db_session, MatchType.ALL, [(ConditionField.NAME, ConditionOperator.CONTAINS, "github")], category.id
    )
    txn = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 1), "GitHub Inc.", [(None, -21.0)]
    )
    count = categorization.run_categorization(db_session)
    assert count == 1

    refreshed = txn_svc.get_transaction(db_session, txn.id)
    split = refreshed.splits[0]
    assert split.category_id is None  # not confirmed automatically
    assert split.suggested_category_id == category.id
    assert split.suggestion_source == SuggestionSource.RULE


def test_rules_exist_but_none_match(db_session, account, category):
    rules_svc.create_rule(
        db_session, MatchType.ALL, [(ConditionField.NAME, ConditionOperator.CONTAINS, "spotify")], category.id
    )
    txn = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 1), "GitHub Inc.", [(None, -21.0)]
    )
    count = categorization.run_categorization(db_session)
    assert count == 0
    refreshed = txn_svc.get_transaction(db_session, txn.id)
    assert refreshed.splits[0].suggested_category_id is None


def test_never_touches_confirmed_categories(db_session, account, category):
    other_category = categories_svc.create_category(db_session, "shared")
    rules_svc.create_rule(
        db_session, MatchType.ALL, [(ConditionField.NAME, ConditionOperator.CONTAINS, "github")], category.id
    )
    txn = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 1), "GitHub Inc.", [(other_category.id, -21.0)]
    )
    categorization.run_categorization(db_session)

    refreshed = txn_svc.get_transaction(db_session, txn.id)
    assert refreshed.splits[0].category_id == other_category.id
    assert refreshed.splits[0].suggested_category_id is None


def test_ignores_multi_split_transactions(db_session, account, category):
    other_category = categories_svc.create_category(db_session, "shared")
    rules_svc.create_rule(
        db_session, MatchType.ALL, [(ConditionField.NAME, ConditionOperator.CONTAINS, "costco")], category.id
    )
    txn = txn_svc.create_transaction(
        db_session,
        account.id,
        dt.date(2026, 1, 1),
        "Costco",
        [(category.id, -60.0), (other_category.id, -20.0)],
    )
    count = categorization.run_categorization(db_session)
    assert count == 0
    refreshed = txn_svc.get_transaction(db_session, txn.id)
    assert all(s.suggested_category_id is None for s in refreshed.splits)


def test_ignores_transfers(db_session, account):
    other = accounts_svc.create_account(
        db_session, name="Card", type=AccountType.LIABILITY, opening_balance=0
    )
    txn_svc.create_transfer(db_session, account.id, other.id, dt.date(2026, 1, 1), "Payment", 10.0)
    count = categorization.run_categorization(db_session)
    assert count == 0


def test_first_match_wins_among_multiple_rules(db_session, account):
    cat_a = categories_svc.create_category(db_session, "a")
    cat_b = categories_svc.create_category(db_session, "b")
    rules_svc.create_rule(
        db_session, MatchType.ALL, [(ConditionField.NAME, ConditionOperator.CONTAINS, "git")], cat_a.id
    )
    rules_svc.create_rule(
        db_session, MatchType.ALL, [(ConditionField.NAME, ConditionOperator.CONTAINS, "github")], cat_b.id
    )
    txn = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 1), "GitHub Inc.", [(None, -21.0)]
    )
    categorization.run_categorization(db_session)
    refreshed = txn_svc.get_transaction(db_session, txn.id)
    assert refreshed.splits[0].suggested_category_id == cat_a.id


def test_scoped_transaction_ids_only_affects_selection(db_session, account, category):
    rules_svc.create_rule(
        db_session, MatchType.ALL, [(ConditionField.NAME, ConditionOperator.CONTAINS, "github")], category.id
    )
    txn1 = txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 1), "GitHub", [(None, -1.0)])
    txn2 = txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 2), "GitHub", [(None, -2.0)])

    count = categorization.run_categorization(db_session, [txn1.id])
    assert count == 1

    refreshed2 = txn_svc.get_transaction(db_session, txn2.id)
    assert refreshed2.splits[0].suggested_category_id is None


def test_rerunning_overwrites_prior_suggestion(db_session, account):
    cat_a = categories_svc.create_category(db_session, "a")
    cat_b = categories_svc.create_category(db_session, "b")
    rule = rules_svc.create_rule(
        db_session, MatchType.ALL, [(ConditionField.NAME, ConditionOperator.CONTAINS, "github")], cat_a.id
    )
    txn = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 1), "GitHub Inc.", [(None, -21.0)]
    )
    categorization.run_categorization(db_session)
    rules_svc.update_rule(db_session, rule.id, target_category_id=cat_b.id)
    categorization.run_categorization(db_session)

    refreshed = txn_svc.get_transaction(db_session, txn.id)
    assert refreshed.splits[0].suggested_category_id == cat_b.id

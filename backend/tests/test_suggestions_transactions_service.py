import datetime as dt

import pytest

from app.errors import NotFoundError, ValidationError
from app.models.account import AccountType
from app.models.rule import ConditionField, ConditionOperator, MatchType
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
def suggested_split(db_session, account):
    category = categories_svc.create_category(db_session, "personal")
    rules_svc.create_rule(
        db_session, MatchType.ALL, [(ConditionField.NAME, ConditionOperator.CONTAINS, "github")], category.id
    )
    txn = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 1), "GitHub Inc.", [(None, -21.0)]
    )
    categorization.run_categorization(db_session)
    refreshed = txn_svc.get_transaction(db_session, txn.id)
    return refreshed, refreshed.splits[0], category


def test_accept_suggestion_sets_category(db_session, suggested_split):
    txn, split, category = suggested_split
    accepted = txn_svc.accept_suggestion(db_session, txn.id, split.id)
    assert accepted.category_id == category.id
    assert accepted.suggested_category_id is None
    assert accepted.suggestion_source is None


def test_reject_suggestion_clears_without_categorizing(db_session, suggested_split):
    txn, split, _category = suggested_split
    rejected = txn_svc.reject_suggestion(db_session, txn.id, split.id)
    assert rejected.category_id is None
    assert rejected.suggested_category_id is None


def test_accept_without_suggestion_rejected(db_session, account):
    txn = txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 1), "x", [(None, -1.0)])
    with pytest.raises(ValidationError):
        txn_svc.accept_suggestion(db_session, txn.id, txn.splits[0].id)


def test_reject_without_suggestion_rejected(db_session, account):
    txn = txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 1), "x", [(None, -1.0)])
    with pytest.raises(ValidationError):
        txn_svc.reject_suggestion(db_session, txn.id, txn.splits[0].id)


def test_accept_missing_transaction_404(db_session):
    with pytest.raises(NotFoundError):
        txn_svc.accept_suggestion(db_session, 999, 1)


def test_accept_missing_split_404(db_session, account):
    txn = txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 1), "x", [(None, -1.0)])
    with pytest.raises(NotFoundError):
        txn_svc.accept_suggestion(db_session, txn.id, 999)

import datetime as dt

import pytest

from app.errors import NotFoundError
from app.models.account import AccountType
from app.models.split import SuggestionSource
from app.services import accounts as accounts_svc
from app.services import ai_categorization as ai_svc
from app.services import categories as categories_svc
from app.services import transactions as txn_svc


@pytest.fixture()
def account(db_session):
    return accounts_svc.create_account(
        db_session, name="Main", type=AccountType.ASSET, opening_balance=1000
    )


@pytest.fixture()
def category(db_session):
    return categories_svc.create_category(db_session, "personal")


def test_list_uncategorized_for_ai(db_session, account, category):
    uncategorized = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 1), "Amazon", [(None, -10.0)]
    )
    txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 2), "Costco", [(category.id, -10.0)]
    )
    eligible = ai_svc.list_uncategorized_for_ai(db_session)
    assert [t.id for t in eligible] == [uncategorized.id]


def test_apply_ai_suggestions(db_session, account, category):
    txn = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 1), "Amazon", [(None, -10.0)]
    )
    split_id = txn.splits[0].id

    result = ai_svc.apply_ai_suggestions(
        db_session,
        [ai_svc.AiSuggestionInput(transaction_id=txn.id, split_id=split_id, category_id=category.id)],
    )
    assert result.applied == 1
    assert result.skipped == []

    refreshed = txn_svc.get_transaction(db_session, txn.id)
    assert refreshed.splits[0].suggested_category_id == category.id
    assert refreshed.splits[0].suggestion_source == SuggestionSource.AI
    assert refreshed.splits[0].category_id is None  # not auto-confirmed


def test_apply_ai_suggestion_skips_already_confirmed_split(db_session, account, category):
    other_category = categories_svc.create_category(db_session, "shared")
    txn = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 1), "Amazon", [(category.id, -10.0)]
    )
    split_id = txn.splits[0].id

    result = ai_svc.apply_ai_suggestions(
        db_session,
        [ai_svc.AiSuggestionInput(transaction_id=txn.id, split_id=split_id, category_id=other_category.id)],
    )
    assert result.applied == 0
    assert result.skipped == [txn.id]

    refreshed = txn_svc.get_transaction(db_session, txn.id)
    assert refreshed.splits[0].category_id == category.id  # untouched
    assert refreshed.splits[0].suggested_category_id is None


def test_apply_ai_suggestion_partial_batch(db_session, account, category):
    confirmed_txn = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 1), "Costco", [(category.id, -5.0)]
    )
    open_txn = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 2), "Amazon", [(None, -10.0)]
    )

    result = ai_svc.apply_ai_suggestions(
        db_session,
        [
            ai_svc.AiSuggestionInput(
                transaction_id=confirmed_txn.id, split_id=confirmed_txn.splits[0].id, category_id=category.id
            ),
            ai_svc.AiSuggestionInput(
                transaction_id=open_txn.id, split_id=open_txn.splits[0].id, category_id=category.id
            ),
        ],
    )
    assert result.applied == 1
    assert result.skipped == [confirmed_txn.id]


def test_apply_ai_suggestion_missing_transaction_404(db_session, category):
    with pytest.raises(NotFoundError):
        ai_svc.apply_ai_suggestions(
            db_session, [ai_svc.AiSuggestionInput(transaction_id=999, split_id=1, category_id=category.id)]
        )


def test_apply_ai_suggestion_missing_split_404(db_session, account, category):
    txn = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 1), "Amazon", [(None, -10.0)]
    )
    with pytest.raises(NotFoundError):
        ai_svc.apply_ai_suggestions(
            db_session,
            [ai_svc.AiSuggestionInput(transaction_id=txn.id, split_id=999, category_id=category.id)],
        )


def test_apply_ai_suggestion_missing_category_404(db_session, account):
    txn = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 1), "Amazon", [(None, -10.0)]
    )
    with pytest.raises(NotFoundError):
        ai_svc.apply_ai_suggestions(
            db_session,
            [ai_svc.AiSuggestionInput(transaction_id=txn.id, split_id=txn.splits[0].id, category_id=999)],
        )


def test_ai_suggestion_goes_through_same_accept_reject_flow(db_session, account, category):
    txn = txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 1), "Amazon", [(None, -10.0)]
    )
    split_id = txn.splits[0].id
    ai_svc.apply_ai_suggestions(
        db_session,
        [ai_svc.AiSuggestionInput(transaction_id=txn.id, split_id=split_id, category_id=category.id)],
    )
    accepted = txn_svc.accept_suggestion(db_session, txn.id, split_id)
    assert accepted.category_id == category.id

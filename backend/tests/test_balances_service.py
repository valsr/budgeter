import datetime as dt

import pytest

from app.models.account import AccountType
from app.services import accounts as accounts_svc
from app.services import transactions as txn_svc
from app.services.balances import compute_balance


def test_balance_with_no_transactions_is_opening_balance(db_session):
    account = accounts_svc.create_account(
        db_session, name="Main", type=AccountType.ASSET, opening_balance=500
    )
    assert compute_balance(db_session, account.id, 500) == 500


def test_balance_reflects_transaction_activity(db_session):
    account = accounts_svc.create_account(
        db_session, name="Main", type=AccountType.ASSET, opening_balance=1000
    )
    txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 1), "Costco", [(None, -88.40)]
    )
    txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 2), "Payroll", [(None, 2140.00)]
    )
    assert compute_balance(db_session, account.id, 1000) == pytest.approx(1000 - 88.40 + 2140.00)


def test_balance_includes_transfer_legs(db_session):
    checking = accounts_svc.create_account(
        db_session, name="Main", type=AccountType.ASSET, opening_balance=1000
    )
    card = accounts_svc.create_account(
        db_session, name="Card", type=AccountType.LIABILITY, opening_balance=-600
    )
    txn_svc.create_transfer(db_session, checking.id, card.id, dt.date(2026, 1, 1), "Payment", 300.0)

    assert compute_balance(db_session, checking.id, 1000) == 700
    assert compute_balance(db_session, card.id, -600) == -300

from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.split import Split
from app.models.transaction import Transaction


def compute_balance(db: Session, account_id: int, opening_balance: float) -> float:
    """Running balance = opening balance + all split activity on this account.

    Transfers are included here (they move real money and must be reflected
    in the account's balance) even though they're excluded from expense/
    income and budget rollups elsewhere.
    """
    total = db.execute(
        select(func.coalesce(func.sum(Split.amount), 0))
        .select_from(Split)
        .join(Transaction, Transaction.id == Split.transaction_id)
        .where(Transaction.account_id == account_id)
    ).scalar_one()
    return float(opening_balance) + float(total)


def compute_balances(db: Session, account_ids: Sequence[int]) -> dict[int, float]:
    """Batch form of compute_balance — one grouped query for all accounts
    instead of one query per account, for endpoints that render a full
    account list. Returns split-activity totals only (no opening balance);
    accounts with no splits are included with a total of 0.
    """
    if not account_ids:
        return {}
    rows = db.execute(
        select(Transaction.account_id, func.coalesce(func.sum(Split.amount), 0))
        .select_from(Split)
        .join(Transaction, Transaction.id == Split.transaction_id)
        .where(Transaction.account_id.in_(account_ids))
        .group_by(Transaction.account_id)
    ).all()
    totals = {account_id: float(total) for account_id, total in rows}
    return {account_id: totals.get(account_id, 0.0) for account_id in account_ids}

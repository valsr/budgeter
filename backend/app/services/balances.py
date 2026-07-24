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

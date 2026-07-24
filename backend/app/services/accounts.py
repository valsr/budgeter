from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import NotFoundError
from app.models.account import Account, AccountType


def _get_or_404(db: Session, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise NotFoundError(f"Account {account_id} not found")
    return account


def create_account(
    db: Session,
    name: str,
    type: AccountType,
    account_number: str | None = None,
    opening_balance: float = 0,
    color: str | None = None,
) -> Account:
    account = Account(
        name=name,
        type=type,
        account_number=account_number,
        opening_balance=opening_balance,
        color=color,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def update_account(
    db: Session,
    account_id: int,
    name: str | None = None,
    type: AccountType | None = None,
    account_number: str | None | object = ...,
    opening_balance: float | None = None,
    color: str | None = None,
) -> Account:
    account = _get_or_404(db, account_id)
    if name is not None:
        account.name = name
    if type is not None:
        account.type = type
    if account_number is not ...:
        account.account_number = account_number
    if opening_balance is not None:
        account.opening_balance = opening_balance
    if color is not None:
        account.color = color
    db.commit()
    db.refresh(account)
    return account


def get_account(db: Session, account_id: int) -> Account:
    return _get_or_404(db, account_id)


def list_accounts(db: Session) -> list[Account]:
    return list(db.execute(select(Account).order_by(Account.id)).scalars().all())

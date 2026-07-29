from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import NotFoundError, ValidationError
from app.models.account import Account, AccountType
from app.models.change import AccountChange, ChangeOperation
from app.models.transaction import Transaction
from app.services import change_log


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

    after = change_log.serialize_account(account)
    change_log.record_change(
        db,
        AccountChange,
        account.id,
        ChangeOperation.CREATE,
        before=None,
        after=after,
        summary=change_log.summarize_account(ChangeOperation.CREATE, None, after),
    )
    db.commit()
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
    before = change_log.serialize_account(account)

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

    after = change_log.serialize_account(account)
    if before != after:
        change_log.record_change(
            db,
            AccountChange,
            account.id,
            ChangeOperation.UPDATE,
            before=before,
            after=after,
            summary=change_log.summarize_account(ChangeOperation.UPDATE, before, after),
        )
        db.commit()
    return account


def get_account(db: Session, account_id: int) -> Account:
    return _get_or_404(db, account_id)


def list_accounts(db: Session) -> list[Account]:
    return list(db.execute(select(Account).order_by(Account.id)).scalars().all())


# --- undo-only helpers -------------------------------------------------
#
# Used exclusively by app/services/undo.py to reverse a CREATE/DELETE
# change record. Not part of the normal CRUD surface: restore_account
# recreates a row with its original id (undoing a delete), and
# hard_delete_account permanently removes a row (undoing a create) rather
# than the archive-style soft delete pattern other entities use — accounts
# have no archive concept, and no normal delete endpoint exists at all.


def restore_account(db: Session, snapshot: dict) -> Account:
    if db.get(Account, snapshot["id"]) is not None:
        raise ValidationError(f"Can't undo: account id {snapshot['id']} is now in use by a different record")

    account = Account(
        id=snapshot["id"],
        name=snapshot["name"],
        account_number=snapshot["account_number"],
        type=AccountType(snapshot["type"]),
        opening_balance=snapshot["opening_balance"],
        color=snapshot["color"],
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    after = change_log.serialize_account(account)
    change_log.record_change(
        db,
        AccountChange,
        account.id,
        ChangeOperation.CREATE,
        before=None,
        after=after,
        summary=change_log.summarize_account(ChangeOperation.CREATE, None, after),
    )
    db.commit()
    return account


def hard_delete_account(db: Session, account_id: int) -> None:
    account = _get_or_404(db, account_id)
    dependent_count = db.execute(
        select(func.count()).select_from(Transaction).where(Transaction.account_id == account_id)
    ).scalar_one()
    if dependent_count:
        raise ValidationError(
            f"Can't undo: {dependent_count} transaction"
            f"{'s' if dependent_count != 1 else ''} now use this account"
        )

    before = change_log.serialize_account(account)
    db.delete(account)
    db.commit()

    change_log.record_change(
        db,
        AccountChange,
        account_id,
        ChangeOperation.DELETE,
        before=before,
        after=None,
        summary=change_log.summarize_account(ChangeOperation.DELETE, before, None),
    )
    db.commit()

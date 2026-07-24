import datetime as dt

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.errors import NotFoundError, ValidationError
from app.models.account import Account
from app.models.category import Category
from app.models.split import Split
from app.models.transaction import Transaction, TransactionType
from app.services.splits import validate_splits

SplitInput = tuple[int | None, float]


def _get_account_or_404(db: Session, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise NotFoundError(f"Account {account_id} not found")
    return account


def _get_transaction_or_404(db: Session, transaction_id: int) -> Transaction:
    txn = db.get(Transaction, transaction_id)
    if txn is None:
        raise NotFoundError(f"Transaction {transaction_id} not found")
    return txn


def create_transaction(
    db: Session,
    account_id: int,
    date: dt.date,
    name: str,
    splits: list[SplitInput],
) -> Transaction:
    _get_account_or_404(db, account_id)
    validate_splits(splits)

    txn = Transaction(account_id=account_id, date=date, name=name, type=TransactionType.NORMAL)
    txn.splits = [Split(category_id=cat_id, amount=amount) for cat_id, amount in splits]
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


def update_transaction_details(
    db: Session,
    transaction_id: int,
    date: dt.date | None = None,
    name: str | None = None,
) -> Transaction:
    txn = _get_transaction_or_404(db, transaction_id)
    if date is not None:
        txn.date = date
    if name is not None:
        txn.name = name
    db.commit()
    db.refresh(txn)
    return txn


def update_transaction_splits(
    db: Session, transaction_id: int, splits: list[SplitInput]
) -> Transaction:
    txn = _get_transaction_or_404(db, transaction_id)
    if txn.type == TransactionType.TRANSFER:
        raise ValidationError("Transfer transactions cannot be split across categories")

    current_total = sum(float(s.amount) for s in txn.splits)
    validate_splits(splits, expected_total=current_total)

    for split in list(txn.splits):
        db.delete(split)
    txn.splits = [Split(category_id=cat_id, amount=amount) for cat_id, amount in splits]
    db.commit()
    db.refresh(txn)
    return txn


def delete_transaction(db: Session, transaction_id: int) -> None:
    txn = _get_transaction_or_404(db, transaction_id)
    if txn.type == TransactionType.TRANSFER and txn.transfer_pair_id is not None:
        pair = db.get(Transaction, txn.transfer_pair_id)
        if pair is not None:
            db.delete(pair)
    db.delete(txn)
    db.commit()


def create_transfer(
    db: Session,
    from_account_id: int,
    to_account_id: int,
    date: dt.date,
    name: str,
    amount: float,
) -> tuple[Transaction, Transaction]:
    if from_account_id == to_account_id:
        raise ValidationError("Transfer must be between two different accounts")
    if amount <= 0:
        raise ValidationError("Transfer amount must be positive")

    _get_account_or_404(db, from_account_id)
    _get_account_or_404(db, to_account_id)

    from_txn = Transaction(
        account_id=from_account_id, date=date, name=name, type=TransactionType.TRANSFER
    )
    from_txn.splits = [Split(category_id=None, amount=-amount)]
    db.add(from_txn)
    db.flush()

    to_txn = Transaction(
        account_id=to_account_id,
        date=date,
        name=name,
        type=TransactionType.TRANSFER,
        transfer_pair_id=from_txn.id,
    )
    to_txn.splits = [Split(category_id=None, amount=amount)]
    db.add(to_txn)
    db.flush()

    from_txn.transfer_pair_id = to_txn.id
    db.commit()
    db.refresh(from_txn)
    db.refresh(to_txn)
    return from_txn, to_txn


def get_transaction(db: Session, transaction_id: int) -> Transaction:
    return _get_transaction_or_404(db, transaction_id)


def _get_split_or_404(db: Session, transaction_id: int, split_id: int) -> Split:
    txn = _get_transaction_or_404(db, transaction_id)
    split = next((s for s in txn.splits if s.id == split_id), None)
    if split is None:
        raise NotFoundError(f"Split {split_id} not found on transaction {transaction_id}")
    return split


def accept_suggestion(db: Session, transaction_id: int, split_id: int) -> Split:
    split = _get_split_or_404(db, transaction_id, split_id)
    if split.suggested_category_id is None:
        raise ValidationError("This split has no pending suggestion to accept")
    split.category_id = split.suggested_category_id
    split.suggested_category_id = None
    split.suggestion_source = None
    db.commit()
    db.refresh(split)
    return split


def reject_suggestion(db: Session, transaction_id: int, split_id: int) -> Split:
    split = _get_split_or_404(db, transaction_id, split_id)
    if split.suggested_category_id is None:
        raise ValidationError("This split has no pending suggestion to reject")
    split.suggested_category_id = None
    split.suggestion_source = None
    db.commit()
    db.refresh(split)
    return split


def _descendant_category_ids(db: Session, category_id: int) -> list[int]:
    children = db.execute(
        select(Category.id).where(Category.parent_id == category_id)
    ).scalars().all()
    return [category_id, *children]


def _base_query(
    account_id: int | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    name_contains: str | None = None,
    category_ids: list[int] | None = None,
) -> Select:
    stmt = select(Transaction).options(selectinload(Transaction.splits))
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    if date_from is not None:
        stmt = stmt.where(Transaction.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Transaction.date <= date_to)
    if name_contains:
        stmt = stmt.where(Transaction.name.ilike(f"%{name_contains}%"))
    if amount_min is not None or amount_max is not None or category_ids is not None:
        stmt = stmt.join(Split, Split.transaction_id == Transaction.id)
        if amount_min is not None:
            stmt = stmt.where(Split.amount >= amount_min)
        if amount_max is not None:
            stmt = stmt.where(Split.amount <= amount_max)
        if category_ids is not None:
            stmt = stmt.where(Split.category_id.in_(category_ids))
    return stmt.distinct()


def list_transactions(
    db: Session,
    account_id: int | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    name_contains: str | None = None,
    category_id: int | None = None,
    page: int = 1,
    page_size: int = 100,
) -> tuple[list[Transaction], int]:
    category_ids = _descendant_category_ids(db, category_id) if category_id is not None else None

    stmt = _base_query(
        account_id, date_from, date_to, amount_min, amount_max, name_contains, category_ids
    )
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    stmt = stmt.order_by(Transaction.date.desc(), Transaction.id.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = list(db.execute(stmt).scalars().unique().all())
    return items, total


def count_uncategorized(db: Session) -> int:
    stmt = (
        select(func.count(func.distinct(Transaction.id)))
        .select_from(Transaction)
        .join(Split, Split.transaction_id == Transaction.id)
        .where(Transaction.type == TransactionType.NORMAL)
        .where(Split.category_id.is_(None))
    )
    return db.execute(stmt).scalar_one()

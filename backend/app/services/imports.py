from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import NotFoundError, ValidationError
from app.models.account import Account
from app.models.import_batch import ImportBatch, ReviewItemStatus, ReviewQueueItem
from app.models.split import Split
from app.models.transaction import Transaction, TransactionType
from app.services.dedupe import ExistingTransaction, MatchType, classify_match
from app.services.qif_parser import parse_qif


def _get_account_or_404(db: Session, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise NotFoundError(f"Account {account_id} not found")
    return account


def _load_existing(db: Session, account_id: int) -> list[ExistingTransaction]:
    rows = db.execute(
        select(Transaction.id, Transaction.date, Transaction.name, func.sum(Split.amount))
        .join(Split, Split.transaction_id == Transaction.id)
        .where(Transaction.account_id == account_id)
        .group_by(Transaction.id)
    ).all()
    return [
        ExistingTransaction(id=row[0], date=row[1], amount=Decimal(str(row[3])), name=row[2])
        for row in rows
    ]


def import_qif(
    db: Session, account_id: int, filename: str, content: str
) -> tuple[ImportBatch, list[int]]:
    _get_account_or_404(db, account_id)
    rows = parse_qif(content)

    existing = _load_existing(db, account_id)
    batch = ImportBatch(filename=filename, account_id=account_id, row_count=len(rows))
    db.add(batch)
    db.flush()

    imported_count = 0
    skipped_count = 0
    review_count = 0
    imported_transaction_ids: list[int] = []

    for row in rows:
        match_type, matched_id = classify_match(row.date, row.amount, row.name, existing)

        if match_type == MatchType.EXACT:
            skipped_count += 1
            continue

        if match_type == MatchType.NEAR:
            review_count += 1
            db.add(
                ReviewQueueItem(
                    import_batch_id=batch.id,
                    account_id=account_id,
                    date=row.date,
                    amount=row.amount,
                    name=row.name,
                    candidate_transaction_id=matched_id,
                    status=ReviewItemStatus.PENDING,
                )
            )
            continue

        txn = Transaction(
            account_id=account_id, date=row.date, name=row.name, type=TransactionType.NORMAL
        )
        txn.splits = [Split(category_id=None, amount=row.amount)]
        db.add(txn)
        db.flush()
        existing.append(ExistingTransaction(id=txn.id, date=row.date, amount=row.amount, name=row.name))
        imported_transaction_ids.append(txn.id)
        imported_count += 1

    batch.imported_count = imported_count
    batch.skipped_duplicate_count = skipped_count
    batch.needs_review_count = review_count
    db.commit()
    db.refresh(batch)
    return batch, imported_transaction_ids


def get_import_batch(db: Session, batch_id: int) -> ImportBatch:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise NotFoundError(f"Import batch {batch_id} not found")
    return batch


def list_import_batches(db: Session) -> list[ImportBatch]:
    return list(
        db.execute(select(ImportBatch).order_by(ImportBatch.imported_at.desc())).scalars().all()
    )


def list_review_items(db: Session, batch_id: int | None = None, pending_only: bool = True) -> list[ReviewQueueItem]:
    stmt = select(ReviewQueueItem)
    if batch_id is not None:
        stmt = stmt.where(ReviewQueueItem.import_batch_id == batch_id)
    if pending_only:
        stmt = stmt.where(ReviewQueueItem.status == ReviewItemStatus.PENDING)
    return list(db.execute(stmt).scalars().all())


def _get_review_item_or_404(db: Session, item_id: int) -> ReviewQueueItem:
    item = db.get(ReviewQueueItem, item_id)
    if item is None:
        raise NotFoundError(f"Review queue item {item_id} not found")
    return item


def resolve_review_item(db: Session, item_id: int, action: str) -> ReviewQueueItem:
    item = _get_review_item_or_404(db, item_id)
    if item.status != ReviewItemStatus.PENDING:
        raise ValidationError(f"Review item {item_id} has already been resolved")

    if action == "new":
        txn = Transaction(
            account_id=item.account_id, date=item.date, name=item.name, type=TransactionType.NORMAL
        )
        txn.splits = [Split(category_id=None, amount=item.amount)]
        db.add(txn)
        item.status = ReviewItemStatus.RESOLVED_NEW
    elif action == "merge":
        if item.candidate_transaction_id is None:
            raise ValidationError("This review item has no candidate transaction to merge into")
        candidate = db.get(Transaction, item.candidate_transaction_id)
        if candidate is None:
            raise NotFoundError(f"Candidate transaction {item.candidate_transaction_id} not found")
        candidate.name = item.name
        item.status = ReviewItemStatus.RESOLVED_MERGED
    elif action == "skip":
        item.status = ReviewItemStatus.RESOLVED_SKIPPED
    else:
        raise ValidationError(f"Unknown review action: {action!r}")

    db.commit()
    db.refresh(item)
    return item

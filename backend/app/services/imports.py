from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import NotFoundError, ValidationError
from app.models.account import Account
from app.models.change import ChangeOperation, TransactionChange
from app.models.import_batch import ImportBatch, ReviewItemStatus, ReviewQueueItem
from app.models.split import Split
from app.models.transaction import Transaction, TransactionType
from app.services import change_log
from app.services.dedupe import ExistingTransaction, MatchType, classify_match
from app.services.qfx_parser import looks_like_qfx, parse_qfx_accounts
from app.services.qif_parser import QifAccountBlock, QifTransaction, parse_qif_accounts


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


def _parse_account_blocks(filename: str, content: str) -> list[QifAccountBlock]:
    """Format-dispatching parse: QFX/OFX by extension or content sniffing,
    QIF otherwise. Both return the same QifAccountBlock shape so the rest of
    the import pipeline doesn't care which format a file was."""
    if looks_like_qfx(filename, content):
        return parse_qfx_accounts(content)
    return parse_qif_accounts(content)


def _import_rows(
    db: Session, account_id: int, filename: str, rows: list[QifTransaction]
) -> tuple[ImportBatch, list[int]]:
    _get_account_or_404(db, account_id)
    existing = _load_existing(db, account_id)
    batch = ImportBatch(filename=filename, account_id=account_id, row_count=len(rows))
    db.add(batch)
    db.flush()

    imported_count = 0
    skipped_count = 0
    review_count = 0
    imported_transaction_ids: list[int] = []
    imported_transactions: list[Transaction] = []

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
        imported_transactions.append(txn)
        imported_count += 1

    batch.imported_count = imported_count
    batch.skipped_duplicate_count = skipped_count
    batch.needs_review_count = review_count
    db.commit()
    db.refresh(batch)

    if imported_transactions:
        total = len(imported_transactions)
        primary_summary = f"Imported {total} transaction{'s' if total != 1 else ''} from '{filename}'"
        group_id: str | None = None
        for index, txn in enumerate(imported_transactions):
            db.refresh(txn)
            after = change_log.serialize_transaction(txn)
            summary = (
                primary_summary
                if index == 0
                else change_log.summarize_transaction(ChangeOperation.CREATE, None, after)
            )
            group_id = change_log.record_change(
                db,
                TransactionChange,
                txn.id,
                ChangeOperation.CREATE,
                before=None,
                after=after,
                summary=summary,
                group_id=group_id,
                is_primary=(index == 0),
            )
        db.commit()

    return batch, imported_transaction_ids


def import_qif(
    db: Session, account_id: int, filename: str, content: str
) -> tuple[ImportBatch, list[int]]:
    blocks = _parse_account_blocks(filename, content)
    rows = [txn for block in blocks for txn in block.transactions]
    return _import_rows(db, account_id, filename, rows)


def detect_accounts(db: Session, filename: str, content: str) -> tuple[bool, list[dict]]:
    """Preview which accounts a file references before importing: which
    match an existing account (by name or account number) and which are
    new. `has_account_sections` is False for a classic single-account QIF
    file (no `!Account` header) — the caller should fall back to letting
    the user pick the target account manually rather than prompting for a
    single unnamed "new account".
    """
    blocks = _parse_account_blocks(filename, content)
    has_sections = any(block.name is not None for block in blocks)

    merged: dict[str | None, dict] = {}
    order: list[str | None] = []
    for block in blocks:
        if block.name not in merged:
            merged[block.name] = {"count": 0, "type_hint": block.account_type_hint}
            order.append(block.name)
        merged[block.name]["count"] += len(block.transactions)

    accounts = db.execute(select(Account)).scalars().all()
    by_name = {a.name.strip().lower(): a.id for a in accounts}
    by_number = {a.account_number.strip().lower(): a.id for a in accounts if a.account_number}

    def _match(name: str | None) -> int | None:
        if name is None:
            return None
        key = name.strip().lower()
        return by_name.get(key) or by_number.get(key)

    # A single-account file's one implicit (name=None) block isn't
    # something to prompt about — the caller falls back to a manual account
    # picker for it entirely, keyed off `has_account_sections` being False.
    results = [
        {
            "parsed_name": name,
            "transaction_count": merged[name]["count"],
            "matched_account_id": _match(name),
            "suggested_type": merged[name]["type_hint"],
        }
        for name in order
        if name is not None
    ]
    return has_sections, results


def import_multi(
    db: Session, filename: str, content: str, resolutions: dict[str | None, int]
) -> tuple[list[ImportBatch], list[int]]:
    """Import every account block in a file, each into the account_id given
    for its parsed name in `resolutions` (built from detect_accounts'
    output, after the caller has resolved/created any new accounts)."""
    blocks = _parse_account_blocks(filename, content)

    merged_rows: dict[str | None, list[QifTransaction]] = {}
    order: list[str | None] = []
    for block in blocks:
        if block.name not in merged_rows:
            merged_rows[block.name] = []
            order.append(block.name)
        merged_rows[block.name].extend(block.transactions)

    # Validate every block has a resolution before importing anything, so a
    # missing one can't leave a partial commit (some accounts imported,
    # others silently skipped).
    missing = [name for name in order if resolutions.get(name) is None]
    if missing:
        labels = ", ".join(repr(name or "this file") for name in missing)
        raise ValidationError(f"No account mapping was provided for: {labels}")

    batches: list[ImportBatch] = []
    all_imported_ids: list[int] = []
    for name in order:
        batch, ids = _import_rows(db, resolutions[name], filename, merged_rows[name])
        batches.append(batch)
        all_imported_ids.extend(ids)
    return batches, all_imported_ids


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

    new_txn: Transaction | None = None
    merge_txn: Transaction | None = None
    merge_before: dict | None = None

    if action == "new":
        txn = Transaction(
            account_id=item.account_id, date=item.date, name=item.name, type=TransactionType.NORMAL
        )
        txn.splits = [Split(category_id=None, amount=item.amount)]
        db.add(txn)
        item.status = ReviewItemStatus.RESOLVED_NEW
        new_txn = txn
    elif action == "merge":
        if item.candidate_transaction_id is None:
            raise ValidationError("This review item has no candidate transaction to merge into")
        candidate = db.get(Transaction, item.candidate_transaction_id)
        if candidate is None:
            raise NotFoundError(f"Candidate transaction {item.candidate_transaction_id} not found")
        merge_before = change_log.serialize_transaction(candidate)
        candidate.name = item.name
        item.status = ReviewItemStatus.RESOLVED_MERGED
        merge_txn = candidate
    elif action == "skip":
        item.status = ReviewItemStatus.RESOLVED_SKIPPED
    else:
        raise ValidationError(f"Unknown review action: {action!r}")

    db.commit()
    db.refresh(item)

    if new_txn is not None:
        db.refresh(new_txn)
        after = change_log.serialize_transaction(new_txn)
        change_log.record_change(
            db,
            TransactionChange,
            new_txn.id,
            ChangeOperation.CREATE,
            before=None,
            after=after,
            summary=change_log.summarize_transaction(ChangeOperation.CREATE, None, after),
        )
        db.commit()
    elif merge_txn is not None:
        db.refresh(merge_txn)
        after = change_log.serialize_transaction(merge_txn)
        if merge_before != after:
            change_log.record_change(
                db,
                TransactionChange,
                merge_txn.id,
                ChangeOperation.UPDATE,
                before=merge_before,
                after=after,
                summary=change_log.summarize_transaction(ChangeOperation.UPDATE, merge_before, after),
            )
            db.commit()

    return item

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import NotFoundError, ValidationError
from app.models.account import Account, AccountType
from app.models.category import Category
from app.models.change import AccountChange, CategoryChange, ChangeOperation, TransactionChange
from app.models.split import Split
from app.models.transaction import Transaction
from app.services import accounts as accounts_service
from app.services import categories as categories_service
from app.services import change_log
from app.services import transactions as transactions_service

_TABLES = (AccountChange, CategoryChange, TransactionChange)

_ENTITY_MODEL = {
    AccountChange: Account,
    CategoryChange: Category,
    TransactionChange: Transaction,
}

_SERIALIZE = {
    AccountChange: change_log.serialize_account,
    CategoryChange: change_log.serialize_category,
    TransactionChange: change_log.serialize_transaction,
}


@dataclass
class UndoOutcome:
    group_id: str
    status: str  # "undone" | "skipped"
    reason: str | None = None


def _find_group(db: Session, group_id: str):
    """A group only ever lives in one of the three tables — probe each in
    turn. Returns (table, rows) ordered by id, or (None, []) if not found."""
    for table in _TABLES:
        rows = list(
            db.execute(select(table).where(table.group_id == group_id).order_by(table.id)).scalars().all()
        )
        if rows:
            return table, rows
    return None, []


def is_stale(db: Session, table, row) -> bool:
    """True if the live entity no longer matches this UPDATE row's `after`
    snapshot — i.e. a newer change has happened since. Non-UPDATE rows are
    never stale (undo-create/undo-delete either succeed outright or are
    blocked by a dependents/collision check, not a "changed since" one)."""
    if row.operation != ChangeOperation.UPDATE:
        return False
    obj = db.get(_ENTITY_MODEL[table], row.entity_id)
    if obj is None:
        return False
    return _SERIALIZE[table](obj) != row.after


def _dependents_blocker(db: Session, table, entity_id: int) -> str | None:
    """For undoing a CREATE (i.e. deleting the row): refuse if anything now
    has a live FK reference to it, rather than silently orphaning/cascading."""
    if table is AccountChange:
        count = db.execute(
            select(func.count()).select_from(Transaction).where(Transaction.account_id == entity_id)
        ).scalar_one()
        if count:
            return f"Can't undo: {count} transaction{'s' if count != 1 else ''} now use this account"
    elif table is CategoryChange:
        child_count = db.execute(
            select(func.count()).select_from(Category).where(Category.parent_id == entity_id)
        ).scalar_one()
        split_count = db.execute(
            select(func.count()).select_from(Split).where(Split.category_id == entity_id)
        ).scalar_one()
        if child_count or split_count:
            parts = []
            if child_count:
                parts.append(f"{child_count} subcategor{'y' if child_count == 1 else 'ies'}")
            if split_count:
                parts.append(f"{split_count} transaction split{'s' if split_count != 1 else ''}")
            return "Can't undo: " + " and ".join(parts) + " now use this category"
    # Transactions have no undo-create dependents check: delete_transaction
    # already handles the only intra-schema reference (its transfer pair).
    return None


def _pk_collision(db: Session, table, entity_id: int) -> bool:
    """For undoing a DELETE (i.e. recreating the row with its original id):
    refuse if that id has since been reassigned to an unrelated row."""
    return db.get(_ENTITY_MODEL[table], entity_id) is not None


def _undo_row(db: Session, table, row) -> None:
    if table is AccountChange:
        if row.operation == ChangeOperation.CREATE:
            accounts_service.hard_delete_account(db, row.entity_id)
        elif row.operation == ChangeOperation.DELETE:
            accounts_service.restore_account(db, row.before)
        else:
            b = row.before
            accounts_service.update_account(
                db,
                row.entity_id,
                name=b["name"],
                type=AccountType(b["type"]),
                account_number=b["account_number"],
                opening_balance=b["opening_balance"],
                color=b["color"],
            )
    elif table is CategoryChange:
        if row.operation == ChangeOperation.CREATE:
            categories_service.hard_delete_category(db, row.entity_id)
        elif row.operation == ChangeOperation.DELETE:
            categories_service.restore_category(db, row.before)
        else:
            categories_service.apply_category_snapshot(db, row.entity_id, row.before)
    else:
        if row.operation == ChangeOperation.CREATE:
            transactions_service.delete_transaction(db, row.entity_id)
        elif row.operation == ChangeOperation.DELETE:
            transactions_service.restore_transaction(db, row.before)
        else:
            transactions_service.apply_transaction_snapshot(db, row.entity_id, row.before)


def _undo_group(db: Session, table, rows: list) -> UndoOutcome:
    group_id = rows[0].group_id
    if rows[0].undone_at is not None:
        return UndoOutcome(group_id, "skipped", "already undone")

    operation = rows[0].operation

    # Pre-flight checks for the two deterministic failure modes, so a
    # blocked CREATE/DELETE-undo never partially applies before failing.
    if operation == ChangeOperation.CREATE:
        for row in rows:
            blocker = _dependents_blocker(db, table, row.entity_id)
            if blocker:
                return UndoOutcome(group_id, "skipped", blocker)
    elif operation == ChangeOperation.DELETE:
        for row in rows:
            if _pk_collision(db, table, row.entity_id):
                return UndoOutcome(
                    group_id,
                    "skipped",
                    f"Can't undo: id {row.entity_id} is now in use by a different record",
                )

    try:
        for row in rows:
            _undo_row(db, table, row)
    except (ValidationError, NotFoundError) as e:
        # UPDATE-undo has no pre-flight check (failures here are rare edge
        # cases, e.g. a snapshot's parent_id no longer exists) — any rows
        # already reverted before the failure keep their own new change
        # records (self-logged), so the data stays consistent even though
        # this group's remaining rows are left un-undone.
        db.commit()
        return UndoOutcome(group_id, "skipped", str(e))

    now = dt.datetime.now(dt.timezone.utc)
    for row in rows:
        row.undone_at = now
    db.commit()
    return UndoOutcome(group_id, "undone")


def undo_groups(db: Session, group_ids: list[str]) -> list[UndoOutcome]:
    """Undo every requested group_id, strict reverse-chronological order
    (by the group's earliest row), best-effort — one group's failure
    doesn't block the rest."""
    found: list[tuple[str, object, list, dt.datetime]] = []
    for group_id in group_ids:
        table, rows = _find_group(db, group_id)
        if table is None:
            found.append((group_id, None, [], dt.datetime.min.replace(tzinfo=dt.timezone.utc)))
        else:
            found.append((group_id, table, rows, min(r.created_at for r in rows)))

    found.sort(key=lambda item: item[3], reverse=True)

    outcomes = []
    for group_id, table, rows, _ in found:
        if table is None:
            outcomes.append(UndoOutcome(group_id, "skipped", "change group not found"))
            continue
        outcomes.append(_undo_group(db, table, rows))
    return outcomes

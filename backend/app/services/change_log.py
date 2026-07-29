import datetime as dt
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.category import Category
from app.models.change import (
    AccountChange,
    CategoryChange,
    ChangeOperation,
    TransactionChange,
)
from app.models.transaction import Transaction

ChangeModel = type[AccountChange] | type[CategoryChange] | type[TransactionChange]

_ALL_CHANGE_TABLES: tuple[ChangeModel, ...] = (AccountChange, CategoryChange, TransactionChange)


def record_change(
    db: Session,
    model: ChangeModel,
    entity_id: int,
    operation: ChangeOperation,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    summary: str,
    *,
    group_id: str | None = None,
    is_primary: bool = True,
) -> str:
    """Write one change row and return its group_id.

    Pass the same group_id into subsequent calls to link rows written by a
    single logical operation (a cascading category archive, a transfer's
    two legs, an import batch's created transactions) so the history page
    collapses them into one entry and undo treats them as one unit.
    """
    group_id = group_id or str(uuid.uuid4())
    db.add(
        model(
            entity_id=entity_id,
            group_id=group_id,
            operation=operation,
            is_primary=is_primary,
            before=before,
            after=after,
            summary=summary,
        )
    )
    purge_expired(db)
    return group_id


def purge_expired(db: Session) -> None:
    from app.services.app_settings import get_retention_days

    retention_days = get_retention_days(db)
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=retention_days)
    for table in _ALL_CHANGE_TABLES:
        db.execute(delete(table).where(table.created_at < cutoff))


# --- snapshot builders -----------------------------------------------------
#
# Plain, JSON-safe dicts (dates/enums/Decimals coerced to str/float) — these
# are frozen-in-time records of what a row looked like, independent of how
# the live schema or related rows may have changed since.


def serialize_account(account: Account) -> dict[str, Any]:
    return {
        "id": account.id,
        "name": account.name,
        "account_number": account.account_number,
        "type": account.type.value,
        "opening_balance": float(account.opening_balance),
        "color": account.color,
    }


def serialize_category(category: Category) -> dict[str, Any]:
    return {
        "id": category.id,
        "name": category.name,
        "parent_id": category.parent_id,
        "color": category.color,
        "sort_order": category.sort_order,
        "archived_at": category.archived_at.isoformat() if category.archived_at else None,
        "is_income": category.is_income,
    }


def serialize_transaction(txn: Transaction) -> dict[str, Any]:
    return {
        "id": txn.id,
        "account_id": txn.account_id,
        "date": txn.date.isoformat(),
        "name": txn.name,
        "type": txn.type.value,
        "transfer_pair_id": txn.transfer_pair_id,
        "splits": [
            {
                "category_id": s.category_id,
                "amount": float(s.amount),
                "suggested_category_id": s.suggested_category_id,
                "suggestion_source": s.suggestion_source.value if s.suggestion_source else None,
            }
            for s in txn.splits
        ],
    }


# --- summary builders --------------------------------------------------


def _diff_lines(before: dict[str, Any], after: dict[str, Any], labels: dict[str, str]) -> list[str]:
    lines = []
    for field, label in labels.items():
        old, new = before.get(field), after.get(field)
        if old != new:
            lines.append(f"{label} changed from {old!r} to {new!r}")
    return lines


_ACCOUNT_FIELD_LABELS = {
    "name": "name",
    "account_number": "account number",
    "type": "type",
    "opening_balance": "opening balance",
    "color": "color",
}

_CATEGORY_FIELD_LABELS = {
    "name": "name",
    "parent_id": "parent category",
    "color": "color",
    "archived_at": "archived state",
    "is_income": "income/expense type",
}

_TRANSACTION_FIELD_LABELS = {
    "date": "date",
    "name": "name",
}


def summarize_account(operation: ChangeOperation, before: dict | None, after: dict | None) -> str:
    if operation == ChangeOperation.CREATE:
        return f"Created account '{after['name']}'"
    if operation == ChangeOperation.DELETE:
        return f"Deleted account '{before['name']}'"

    if before["name"] != after["name"]:
        return f"Renamed account '{before['name']}' to '{after['name']}'"
    label = after["name"]
    diffs = _diff_lines(before, after, _ACCOUNT_FIELD_LABELS)
    return f"Updated account '{label}': " + "; ".join(diffs) if diffs else f"Updated account '{label}'"


def summarize_category(operation: ChangeOperation, before: dict | None, after: dict | None) -> str:
    if operation == ChangeOperation.CREATE:
        return f"Created category '{after['name']}'"
    if operation == ChangeOperation.DELETE:
        return f"Deleted category '{before['name']}'"

    if before["name"] != after["name"]:
        return f"Renamed category '{before['name']}' to '{after['name']}'"
    label = after["name"]
    diffs = _diff_lines(before, after, _CATEGORY_FIELD_LABELS)
    return f"Updated category '{label}': " + "; ".join(diffs) if diffs else f"Updated category '{label}'"


def _total_amount(snapshot: dict) -> float:
    return sum(s["amount"] for s in snapshot["splits"])


def summarize_transaction(operation: ChangeOperation, before: dict | None, after: dict | None) -> str:
    if operation == ChangeOperation.CREATE:
        return f"Created transaction '{after['name']}' (${_total_amount(after):.2f})"
    if operation == ChangeOperation.DELETE:
        return f"Deleted transaction '{before['name']}' (${_total_amount(before):.2f})"

    label = after["name"]
    diffs = _diff_lines(before, after, _TRANSACTION_FIELD_LABELS)
    if before["splits"] != after["splits"]:
        diffs.append("splits changed")
    return f"Updated transaction '{label}': " + "; ".join(diffs) if diffs else f"Updated transaction '{label}'"

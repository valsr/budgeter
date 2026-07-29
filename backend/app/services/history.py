import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ValidationError
from app.models.change import AccountChange, CategoryChange, ChangeOperation, TransactionChange
from app.services import undo as undo_service

_TABLES_BY_ENTITY_TYPE = {
    "account": AccountChange,
    "category": CategoryChange,
    "transaction": TransactionChange,
}


@dataclass
class ChangeItemData:
    entity_id: int
    before: dict | None
    after: dict | None


@dataclass
class ChangeGroupData:
    group_id: str
    entity_type: str
    operation: ChangeOperation
    summary: str
    created_at: dt.datetime
    undone_at: dt.datetime | None
    is_stale: bool
    items: list[ChangeItemData]


def _tables_for(entity_type: str | None):
    if entity_type is None:
        return list(_TABLES_BY_ENTITY_TYPE.items())
    if entity_type not in _TABLES_BY_ENTITY_TYPE:
        raise ValidationError(f"Unknown entity_type: {entity_type!r}")
    return [(entity_type, _TABLES_BY_ENTITY_TYPE[entity_type])]


def list_changes(
    db: Session,
    entity_type: str | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[ChangeGroupData], int]:
    rows: list[tuple[str, type, object]] = []
    for type_name, table in _tables_for(entity_type):
        stmt = select(table)
        if date_from is not None:
            stmt = stmt.where(table.created_at >= dt.datetime.combine(date_from, dt.time.min, dt.timezone.utc))
        if date_to is not None:
            stmt = stmt.where(table.created_at <= dt.datetime.combine(date_to, dt.time.max, dt.timezone.utc))
        for row in db.execute(stmt).scalars().all():
            rows.append((type_name, table, row))

    groups: dict[str, list[tuple[str, type, object]]] = {}
    for entry in rows:
        groups.setdefault(entry[2].group_id, []).append(entry)

    ordered_groups = []
    for group_id, items in groups.items():
        items.sort(key=lambda entry: entry[2].id)
        latest = max(entry[2].created_at for entry in items)
        ordered_groups.append((group_id, items, latest))
    ordered_groups.sort(key=lambda g: g[2], reverse=True)

    total = len(ordered_groups)
    start = (page - 1) * page_size
    page_slice = ordered_groups[start : start + page_size]

    results = []
    for group_id, items, latest in page_slice:
        type_name, table, primary_row = next(
            (entry for entry in items if entry[2].is_primary), items[0]
        )
        results.append(
            ChangeGroupData(
                group_id=group_id,
                entity_type=type_name,
                operation=primary_row.operation,
                summary=primary_row.summary,
                created_at=latest,
                undone_at=primary_row.undone_at,
                is_stale=any(undo_service.is_stale(db, t, r) for _, t, r in items),
                items=[
                    ChangeItemData(entity_id=r.entity_id, before=r.before, after=r.after)
                    for _, _, r in items
                ],
            )
        )
    return results, total

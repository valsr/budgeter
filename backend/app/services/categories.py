from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import NotFoundError, ValidationError
from app.models.category import Category
from app.models.change import CategoryChange, ChangeOperation
from app.models.split import Split
from app.services import change_log


def _get_or_404(db: Session, category_id: int) -> Category:
    category = db.get(Category, category_id)
    if category is None:
        raise NotFoundError(f"Category {category_id} not found")
    return category


def _next_sort_order(db: Session, parent_id: int | None) -> int:
    max_order = db.execute(
        select(func.max(Category.sort_order)).where(Category.parent_id == parent_id)
    ).scalar()
    return 0 if max_order is None else max_order + 1


def _is_in_subtree(db: Session, root_id: int, candidate_id: int) -> bool:
    """True if candidate_id is root_id itself, or anywhere in root_id's
    subtree at any depth — used to block reparenting a category under one
    of its own descendants (which would create a cycle)."""
    frontier = [root_id]
    while frontier:
        current = frontier.pop()
        if current == candidate_id:
            return True
        frontier.extend(db.execute(select(Category.id).where(Category.parent_id == current)).scalars().all())
    return False


def create_category(
    db: Session,
    name: str,
    parent_id: int | None = None,
    color: str | None = None,
) -> Category:
    if parent_id is not None:
        _get_or_404(db, parent_id)

    category = Category(
        name=name,
        parent_id=parent_id,
        color=color,
        sort_order=_next_sort_order(db, parent_id),
    )
    db.add(category)
    db.commit()
    db.refresh(category)

    after = change_log.serialize_category(category)
    change_log.record_change(
        db,
        CategoryChange,
        category.id,
        ChangeOperation.CREATE,
        before=None,
        after=after,
        summary=change_log.summarize_category(ChangeOperation.CREATE, None, after),
    )
    db.commit()
    return category


def update_category(
    db: Session,
    category_id: int,
    name: str | None = None,
    color: str | None = None,
    parent_id: int | None | object = ...,
) -> Category:
    category = _get_or_404(db, category_id)
    before = change_log.serialize_category(category)

    if name is not None:
        category.name = name
    if color is not None:
        category.color = color

    if parent_id is not ...:
        if parent_id == category_id:
            raise ValidationError("A category cannot be its own parent")
        if parent_id is not None:
            _get_or_404(db, parent_id)
            if _is_in_subtree(db, category_id, parent_id):
                raise ValidationError("Cannot make a category a child of its own descendant")
        if parent_id != category.parent_id:
            category.parent_id = parent_id
            category.sort_order = _next_sort_order(db, parent_id)

    db.commit()
    db.refresh(category)

    after = change_log.serialize_category(category)
    if before != after:
        change_log.record_change(
            db,
            CategoryChange,
            category.id,
            ChangeOperation.UPDATE,
            before=before,
            after=after,
            summary=change_log.summarize_category(ChangeOperation.UPDATE, before, after),
        )
        db.commit()
    return category


def archive_category(db: Session, category_id: int) -> Category:
    category = _get_or_404(db, category_id)
    now = datetime.now(timezone.utc)

    before_by_id = {category.id: change_log.serialize_category(category)}
    category.archived_at = now
    affected = [category]

    # Cascade through the whole subtree, not just direct children — a
    # category can be nested arbitrarily deep.
    frontier = [category_id]
    while frontier:
        children = db.execute(select(Category).where(Category.parent_id == frontier.pop())).scalars().all()
        for child in children:
            before_by_id[child.id] = change_log.serialize_category(child)
            child.archived_at = now
            affected.append(child)
            frontier.append(child.id)

    db.commit()
    for c in affected:
        db.refresh(c)

    descendant_count = len(affected) - 1
    if descendant_count:
        plural = "y" if descendant_count == 1 else "ies"
        primary_summary = f"Archived '{category.name}' and {descendant_count} subcategor{plural}"
    else:
        primary_summary = f"Archived '{category.name}'"

    group_id: str | None = None
    for index, child in enumerate(affected):
        after = change_log.serialize_category(child)
        summary = (
            primary_summary
            if index == 0
            else change_log.summarize_category(ChangeOperation.UPDATE, before_by_id[child.id], after)
        )
        group_id = change_log.record_change(
            db,
            CategoryChange,
            child.id,
            ChangeOperation.UPDATE,
            before=before_by_id[child.id],
            after=after,
            summary=summary,
            group_id=group_id,
            is_primary=(index == 0),
        )
    db.commit()
    return category


def reorder_categories(
    db: Session, parent_id: int | None, ordered_ids: list[int]
) -> list[Category]:
    siblings = (
        db.execute(select(Category).where(Category.parent_id == parent_id))
        .scalars()
        .all()
    )
    sibling_ids = {c.id for c in siblings}
    if sibling_ids != set(ordered_ids):
        raise ValidationError(
            "ordered_ids must contain exactly the current sibling set"
        )

    by_id = {c.id: c for c in siblings}
    for index, cat_id in enumerate(ordered_ids):
        by_id[cat_id].sort_order = index
    db.commit()
    return [by_id[cat_id] for cat_id in ordered_ids]


def list_categories(db: Session, include_archived: bool = False) -> list[Category]:
    stmt = select(Category).where(Category.parent_id.is_(None))
    if not include_archived:
        stmt = stmt.where(Category.archived_at.is_(None))
    stmt = stmt.order_by(Category.sort_order)
    roots = db.execute(stmt).scalars().all()
    return list(roots)


def get_category(db: Session, category_id: int) -> Category:
    return _get_or_404(db, category_id)


PATH_DELIMITER = ":"


def resolve_category_path(db: Session, path: str) -> Category:
    """Find-or-create a category by a colon-delimited path, e.g.
    "shared:groceries:alcohol" (docs/requirements.md §2.2's own example,
    `shared → groceries → alcohol`). Each segment is matched
    case-insensitively against existing non-archived siblings at that
    level; a segment with no match is created. Returns the final (leaf)
    category.

    Matching only considers non-archived siblings — same scope pickers use
    — so typing a path that happens to match an archived category's name
    creates a fresh active one rather than silently reviving the archived
    one.
    """
    segments = [s.strip() for s in path.split(PATH_DELIMITER)]
    if not segments or any(s == "" for s in segments):
        raise ValidationError("Category path segments cannot be empty")

    parent_id: int | None = None
    category: Category | None = None
    for segment in segments:
        siblings = (
            db.execute(
                select(Category)
                .where(Category.parent_id == parent_id)
                .where(Category.archived_at.is_(None))
            )
            .scalars()
            .all()
        )
        match = next((c for c in siblings if c.name.casefold() == segment.casefold()), None)
        category = match if match is not None else create_category(db, name=segment, parent_id=parent_id)
        parent_id = category.id

    assert category is not None  # segments is non-empty, so the loop ran at least once
    return category


# --- undo-only helpers -------------------------------------------------
#
# Used exclusively by app/services/undo.py. apply_category_snapshot covers
# every mutable field a CategoryChange row can carry — including
# archived_at, which update_category's public signature deliberately
# doesn't expose (archiving goes through the dedicated archive_category
# cascade) — so undoing either a plain edit or an archive/un-archive goes
# through the same path. restore_category/hard_delete_category mirror the
# accounts.py pair for undoing a delete/create (categories have no hard
# delete in the normal CRUD surface, only the archive soft-delete).


def apply_category_snapshot(db: Session, category_id: int, snapshot: dict) -> Category:
    category = _get_or_404(db, category_id)
    before = change_log.serialize_category(category)

    category.name = snapshot["name"]
    category.color = snapshot["color"]
    category.parent_id = snapshot["parent_id"]
    category.sort_order = snapshot["sort_order"]
    category.archived_at = (
        datetime.fromisoformat(snapshot["archived_at"]) if snapshot["archived_at"] else None
    )

    db.commit()
    db.refresh(category)

    after = change_log.serialize_category(category)
    if before != after:
        change_log.record_change(
            db,
            CategoryChange,
            category.id,
            ChangeOperation.UPDATE,
            before=before,
            after=after,
            summary=change_log.summarize_category(ChangeOperation.UPDATE, before, after),
        )
        db.commit()
    return category


def restore_category(db: Session, snapshot: dict) -> Category:
    if db.get(Category, snapshot["id"]) is not None:
        raise ValidationError(f"Can't undo: category id {snapshot['id']} is now in use by a different record")

    category = Category(
        id=snapshot["id"],
        name=snapshot["name"],
        parent_id=snapshot["parent_id"],
        color=snapshot["color"],
        sort_order=snapshot["sort_order"],
        archived_at=datetime.fromisoformat(snapshot["archived_at"]) if snapshot["archived_at"] else None,
    )
    db.add(category)
    db.commit()
    db.refresh(category)

    after = change_log.serialize_category(category)
    change_log.record_change(
        db,
        CategoryChange,
        category.id,
        ChangeOperation.CREATE,
        before=None,
        after=after,
        summary=change_log.summarize_category(ChangeOperation.CREATE, None, after),
    )
    db.commit()
    return category


def hard_delete_category(db: Session, category_id: int) -> None:
    category = _get_or_404(db, category_id)
    child_count = db.execute(
        select(func.count()).select_from(Category).where(Category.parent_id == category_id)
    ).scalar_one()
    split_count = db.execute(
        select(func.count()).select_from(Split).where(Split.category_id == category_id)
    ).scalar_one()
    if child_count or split_count:
        parts = []
        if child_count:
            parts.append(f"{child_count} subcategor{'y' if child_count == 1 else 'ies'}")
        if split_count:
            parts.append(f"{split_count} transaction split{'s' if split_count != 1 else ''}")
        raise ValidationError("Can't undo: " + " and ".join(parts) + " now use this category")

    before = change_log.serialize_category(category)
    db.delete(category)
    db.commit()

    change_log.record_change(
        db,
        CategoryChange,
        category_id,
        ChangeOperation.DELETE,
        before=before,
        after=None,
        summary=change_log.summarize_category(ChangeOperation.DELETE, before, None),
    )
    db.commit()

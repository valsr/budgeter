from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import NotFoundError, ValidationError
from app.models.category import Category


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
    return category


def update_category(
    db: Session,
    category_id: int,
    name: str | None = None,
    color: str | None = None,
    parent_id: int | None | object = ...,
) -> Category:
    category = _get_or_404(db, category_id)

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
    return category


def archive_category(db: Session, category_id: int) -> Category:
    category = _get_or_404(db, category_id)
    now = datetime.now(timezone.utc)
    category.archived_at = now

    # Cascade through the whole subtree, not just direct children — a
    # category can be nested arbitrarily deep.
    frontier = [category_id]
    while frontier:
        children = db.execute(select(Category).where(Category.parent_id == frontier.pop())).scalars().all()
        for child in children:
            child.archived_at = now
            frontier.append(child.id)

    db.commit()
    db.refresh(category)
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

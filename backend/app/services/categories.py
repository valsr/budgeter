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


def create_category(
    db: Session,
    name: str,
    parent_id: int | None = None,
    color: str | None = None,
) -> Category:
    if parent_id is not None:
        parent = _get_or_404(db, parent_id)
        if parent.parent_id is not None:
            raise ValidationError("Categories can only be nested one level deep")

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
            parent = _get_or_404(db, parent_id)
            if parent.parent_id is not None:
                raise ValidationError("Categories can only be nested one level deep")
            if any(child.id == parent_id for child in category.children):
                raise ValidationError("Cannot make a category a child of its own child")
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
    for child in category.children:
        child.archived_at = now
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

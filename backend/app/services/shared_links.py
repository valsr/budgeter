"""A user's mapping of their own categories onto a shared budget's categories. The links live in
the user's books; the shared category ids they name point into the shared budget's file."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ValidationError
from app.models import Category, SharedCategoryLink


def get_links(
    db: Session, budget_id: int, valid_shared_ids: set[int] | None = None
) -> list[SharedCategoryLink]:
    """The caller's links for one shared budget. With `valid_shared_ids`, links to shared
    categories outside that set (since deleted from the shared budget) are left out."""
    links = db.execute(
        select(SharedCategoryLink)
        .where(SharedCategoryLink.shared_budget_id == budget_id)
        .order_by(SharedCategoryLink.id)
    ).scalars()
    if valid_shared_ids is None:
        return list(links)
    return [link for link in links if link.shared_category_id in valid_shared_ids]


def set_links(
    db: Session, budget_id: int, links: list[tuple[int, int]], valid_shared_ids: set[int]
) -> list[SharedCategoryLink]:
    """Replace all of the caller's links for one shared budget with `links`, given as
    (category_id, shared_category_id) pairs."""
    category_ids = [category_id for category_id, _ in links]
    if len(set(category_ids)) != len(category_ids):
        raise ValidationError("A category can only be linked once per shared budget")
    existing = set(
        db.execute(select(Category.id).where(Category.id.in_(category_ids))).scalars()
    )
    for category_id, shared_category_id in links:
        if category_id not in existing:
            raise ValidationError(f"Category {category_id} not found")
        if shared_category_id not in valid_shared_ids:
            raise ValidationError(f"Shared category {shared_category_id} not found")

    # Row by row rather than a bulk delete, so the books commit hook sees the change.
    for link in get_links(db, budget_id):
        db.delete(link)
    db.flush()
    new = [
        SharedCategoryLink(
            category_id=category_id, shared_budget_id=budget_id, shared_category_id=shared_category_id
        )
        for category_id, shared_category_id in links
    ]
    db.add_all(new)
    db.commit()
    return new

"""Category tree and monthly amounts inside one shared budget's file."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import NotFoundError, ValidationError
from app.shared_models import SharedBudgetAmount, SharedCategory

_UNSET = object()


def list_categories(sh: Session) -> list[SharedCategory]:
    return list(
        sh.execute(select(SharedCategory).order_by(SharedCategory.sort_order, SharedCategory.name)).scalars()
    )


def _get(sh: Session, category_id: int) -> SharedCategory:
    cat = sh.get(SharedCategory, category_id)
    if cat is None:
        raise NotFoundError("Category not found")
    return cat


def _check_name(name: str) -> str:
    name = (name or "").strip()
    if not name or len(name) > 200:
        raise ValidationError("A category name must be 1-200 characters")
    return name


def create_category(sh: Session, name: str, parent_id: int | None, is_income: bool) -> SharedCategory:
    name = _check_name(name)
    if parent_id is not None and sh.get(SharedCategory, parent_id) is None:
        raise ValidationError("Parent category not found")
    cat = SharedCategory(name=name, parent_id=parent_id, is_income=is_income)
    sh.add(cat)
    sh.commit()
    return cat


def update_category(
    sh: Session,
    category_id: int,
    *,
    name: str | None = None,
    parent_id=_UNSET,
    sort_order: int | None = None,
    is_income: bool | None = None,
    archived: bool | None = None,
) -> SharedCategory:
    cat = _get(sh, category_id)
    if name is not None:
        cat.name = _check_name(name)
    if parent_id is not _UNSET:
        if parent_id is not None:
            parent = sh.get(SharedCategory, parent_id)
            if parent is None:
                raise ValidationError("Parent category not found")
            node = parent
            while node is not None:
                if node.id == cat.id:
                    raise ValidationError("A category can't be moved under itself")
                node = node.parent
        cat.parent_id = parent_id
    if sort_order is not None:
        cat.sort_order = sort_order
    if is_income is not None:
        cat.is_income = is_income
    if archived is not None:
        cat.archived_at = datetime.now(timezone.utc) if archived else None
    sh.commit()
    return cat


def delete_category(sh: Session, category_id: int) -> None:
    cat = _get(sh, category_id)
    if sh.execute(select(SharedCategory.id).where(SharedCategory.parent_id == cat.id).limit(1)).first():
        raise ValidationError("Delete or move its subcategories first")
    sh.delete(cat)
    sh.commit()


def get_amounts(sh: Session, year: int) -> list[SharedBudgetAmount]:
    return list(
        sh.execute(
            select(SharedBudgetAmount)
            .where(SharedBudgetAmount.year == year)
            .order_by(SharedBudgetAmount.shared_category_id, SharedBudgetAmount.month)
        ).scalars()
    )


def set_amounts(sh: Session, year: int, lines: list[tuple[int, int, Decimal | None]]) -> None:
    """Upsert (category_id, month, amount) lines; a None amount deletes that cell."""
    known = set(sh.execute(select(SharedCategory.id)).scalars())
    for category_id, month, _ in lines:
        if not 1 <= month <= 12:
            raise ValidationError("Month must be between 1 and 12")
        if category_id not in known:
            raise ValidationError("Category not found")
    for category_id, month, amount in lines:
        existing = sh.execute(
            select(SharedBudgetAmount).where(
                SharedBudgetAmount.shared_category_id == category_id,
                SharedBudgetAmount.year == year,
                SharedBudgetAmount.month == month,
            )
        ).scalar_one_or_none()
        if amount is None:
            if existing is not None:
                sh.delete(existing)
        elif existing is not None:
            existing.amount = amount
        else:
            sh.add(SharedBudgetAmount(shared_category_id=category_id, year=year, month=month, amount=amount))
        sh.flush()
    sh.commit()

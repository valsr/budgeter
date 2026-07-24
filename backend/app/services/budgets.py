from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.errors import NotFoundError, ValidationError
from app.models.budget import Budget, BudgetAmount, BudgetCategory
from app.models.category import Category
from app.models.split import Split
from app.models.transaction import Transaction, TransactionType
from app.services.budget_rollup import ReportRow, build_row, sum_monthly

CategoryInput = tuple[int, dict[int, float]]  # (category_id, {month: amount})


def _get_budget_or_404(db: Session, budget_id: int) -> Budget:
    budget = db.get(Budget, budget_id)
    if budget is None:
        raise NotFoundError(f"Budget {budget_id} not found")
    return budget


def _is_leaf_category(db: Session, category_id: int) -> bool:
    child_count = db.execute(
        select(func.count()).select_from(Category).where(Category.parent_id == category_id)
    ).scalar_one()
    return child_count == 0


def _validate_categories(db: Session, categories: list[CategoryInput]) -> None:
    for category_id, _monthly in categories:
        category = db.get(Category, category_id)
        if category is None:
            raise NotFoundError(f"Category {category_id} not found")
        if not _is_leaf_category(db, category_id):
            raise ValidationError(
                f"Category {category_id} has children; only leaf categories can be directly budgeted"
            )


def _build_budget_categories(categories: list[CategoryInput], year: int) -> list[BudgetCategory]:
    result = []
    for category_id, monthly in categories:
        bc = BudgetCategory(category_id=category_id)
        bc.amounts = [
            BudgetAmount(year=year, month=month, amount=amount) for month, amount in monthly.items()
        ]
        result.append(bc)
    return result


def create_budget(db: Session, name: str, categories: list[CategoryInput], year: int) -> Budget:
    _validate_categories(db, categories)
    budget = Budget(name=name)
    budget.budget_categories = _build_budget_categories(categories, year)
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return budget


def update_budget(
    db: Session,
    budget_id: int,
    name: str | None = None,
    categories: list[CategoryInput] | None = None,
    year: int | None = None,
) -> Budget:
    budget = _get_budget_or_404(db, budget_id)
    if name is not None:
        budget.name = name
    if categories is not None:
        if year is None:
            raise ValidationError("year is required when replacing budget categories")
        _validate_categories(db, categories)
        for bc in list(budget.budget_categories):
            db.delete(bc)
        budget.budget_categories = _build_budget_categories(categories, year)
    db.commit()
    db.refresh(budget)
    return budget


def delete_budget(db: Session, budget_id: int) -> None:
    budget = _get_budget_or_404(db, budget_id)
    db.delete(budget)
    db.commit()


def list_budgets(db: Session) -> list[Budget]:
    return list(db.execute(select(Budget).order_by(Budget.id)).scalars().all())


def get_budget(db: Session, budget_id: int) -> Budget:
    stmt = (
        select(Budget)
        .options(selectinload(Budget.budget_categories).selectinload(BudgetCategory.amounts))
        .where(Budget.id == budget_id)
    )
    budget = db.execute(stmt).scalars().first()
    if budget is None:
        raise NotFoundError(f"Budget {budget_id} not found")
    return budget


def _actuals_for_category(
    db: Session, category_id: int, year: int, through_month: int
) -> dict[int, Decimal]:
    rows = db.execute(
        select(func.strftime("%m", Transaction.date), func.sum(Split.amount))
        .select_from(Split)
        .join(Transaction, Transaction.id == Split.transaction_id)
        .where(Split.category_id == category_id)
        .where(Transaction.type == TransactionType.NORMAL)
        .where(func.strftime("%Y", Transaction.date) == str(year))
        .group_by(func.strftime("%m", Transaction.date))
    ).all()
    # Positive "actual spend": ledger withdrawals are negative amounts, so negate.
    actuals = {int(month_str): -Decimal(str(total)) for month_str, total in rows}
    return {m: v for m, v in actuals.items() if m <= through_month}


def get_report(db: Session, budget_id: int, year: int, through_month: int) -> list[ReportRow]:
    budget = get_budget(db, budget_id)
    months = list(range(1, through_month + 1))

    leaf_ids = [bc.category_id for bc in budget.budget_categories]
    if not leaf_ids:
        return []

    categories_by_id = {
        c.id: c
        for c in db.execute(select(Category).where(Category.id.in_(leaf_ids))).scalars().all()
    }
    parent_ids = {c.parent_id for c in categories_by_id.values() if c.parent_id is not None}
    if parent_ids:
        for parent in db.execute(select(Category).where(Category.id.in_(parent_ids))).scalars().all():
            categories_by_id[parent.id] = parent

    budgeted_by_category: dict[int, dict[int, Decimal]] = {}
    for bc in budget.budget_categories:
        budgeted_by_category[bc.category_id] = {
            a.month: Decimal(str(a.amount)) for a in bc.amounts if a.year == year
        }

    actual_by_category = {
        cat_id: _actuals_for_category(db, cat_id, year, through_month) for cat_id in leaf_ids
    }

    # Group leaves by parent, preserving each group's global display order
    # (Category.sort_order is the single source of truth for category
    # ordering everywhere in the app, per docs/requirements.md §2.2).
    leaves_by_parent: dict[int | None, list[Category]] = {}
    for cat_id in leaf_ids:
        leaf = categories_by_id[cat_id]
        leaves_by_parent.setdefault(leaf.parent_id, []).append(leaf)
    for group in leaves_by_parent.values():
        group.sort(key=lambda c: c.sort_order)

    # Top-level entries are either a parent-with-included-children group, or
    # a standalone top-level category that's itself a leaf; both are
    # siblings at the top level and must interleave by global sort_order.
    top_level_entries: list[tuple[int, int | None, Category | None]] = []
    for parent_id in leaves_by_parent:
        if parent_id is None:
            for leaf in leaves_by_parent[None]:
                top_level_entries.append((leaf.sort_order, None, leaf))
        else:
            parent = categories_by_id[parent_id]
            top_level_entries.append((parent.sort_order, parent_id, None))
    top_level_entries.sort(key=lambda e: e[0])

    rows: list[ReportRow] = []
    for _sort_order, parent_id, standalone_leaf in top_level_entries:
        if standalone_leaf is not None:
            rows.append(
                build_row(
                    standalone_leaf.id,
                    standalone_leaf.name,
                    False,
                    budgeted_by_category[standalone_leaf.id],
                    actual_by_category[standalone_leaf.id],
                    months,
                    through_month,
                )
            )
            continue

        children = leaves_by_parent[parent_id]
        parent_budgeted = sum_monthly([budgeted_by_category[c.id] for c in children])
        parent_actual = sum_monthly([actual_by_category[c.id] for c in children])
        rows.append(
            build_row(
                parent_id, categories_by_id[parent_id].name, True, parent_budgeted, parent_actual, months, through_month
            )
        )
        for child in children:
            rows.append(
                build_row(
                    child.id,
                    child.name,
                    False,
                    budgeted_by_category[child.id],
                    actual_by_category[child.id],
                    months,
                    through_month,
                )
            )

    return rows

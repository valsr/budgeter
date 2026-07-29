from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.errors import NotFoundError, ValidationError
from app.models.budget import Budget, BudgetAmount, BudgetCategory
from app.models.category import Category
from app.models.split import Split
from app.models.transaction import Transaction, TransactionType
from app.services.budget_rollup import MonthlyAmounts, ReportRow, build_row, sum_monthly

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
        # Flush the deletes before adding replacement rows -- otherwise a
        # category kept across the edit (the common case: amounts changed,
        # selection didn't) collides with itself on the (budget_id,
        # category_id) unique constraint, since the old row hasn't been
        # removed from the table yet when the new one is inserted.
        db.flush()
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


def _assemble_rows(
    db: Session,
    leaf_ids: list[int],
    budgeted_by_category: dict[int, dict[int, Decimal]],
    has_budget_by_category: dict[int, bool],
    year: int,
    through_month: int,
) -> list[ReportRow]:
    """Build report rows for a set of budgeted leaves plus every one of
    their ancestors, at any depth — an ancestor's budgeted/actual amounts
    are always the sum of its children (docs/requirements.md §2.2: "Parent
    category values ... are always derived"), recursively.
    """
    months = list(range(1, through_month + 1))
    if not leaf_ids:
        return []

    # Load every leaf plus every ancestor above it, however deep.
    categories_by_id: dict[int, Category] = {}
    to_load = set(leaf_ids)
    while to_load:
        batch = db.execute(select(Category).where(Category.id.in_(to_load))).scalars().all()
        to_load = set()
        for cat in batch:
            categories_by_id[cat.id] = cat
            if cat.parent_id is not None and cat.parent_id not in categories_by_id:
                to_load.add(cat.parent_id)

    def is_income_effective(cat_id: int) -> bool:
        """A category counts as income if it or any ancestor is marked
        is_income -- marking a top-level "Income" category flips its whole
        subtree without having to tag every leaf underneath it."""
        cat: Category | None = categories_by_id.get(cat_id)
        while cat is not None:
            if cat.is_income:
                return True
            cat = categories_by_id.get(cat.parent_id) if cat.parent_id is not None else None
        return False

    actual_by_category = {
        cat_id: _actuals_for_category(db, cat_id, year, through_month) for cat_id in leaf_ids
    }
    # Reporting-only sign flip: deposits into an income category are positive
    # splits, which _actuals_for_category negates into a negative "actual"
    # (the convention that makes expense spend read as a positive number).
    # Negating again for income leaves undoes that, so income reads as a
    # natural positive amount received. Doesn't touch the underlying splits.
    for cat_id in leaf_ids:
        if is_income_effective(cat_id):
            actual_by_category[cat_id] = {m: -v for m, v in actual_by_category[cat_id].items()}

    # Children, keyed by parent_id (None for top-level), restricted to
    # categories actually involved here (a leaf or an ancestor of one) —
    # sibling branches with no budgeted leaf underneath them are excluded.
    # Category.sort_order is the single source of truth for display order
    # everywhere in the app (docs/requirements.md §2.2).
    children_of: dict[int | None, list[int]] = {}
    for cat_id, cat in categories_by_id.items():
        children_of.setdefault(cat.parent_id, []).append(cat_id)
    for group in children_of.values():
        group.sort(key=lambda cid: categories_by_id[cid].sort_order)

    # Bottom-up rollup: a leaf's own budgeted/actual/has_budget, or a
    # parent's summed-from-children values, memoized since the same
    # ancestor is reached once per child but should only be computed once.
    monthly_cache: dict[int, tuple[MonthlyAmounts, MonthlyAmounts]] = {}
    has_budget_cache: dict[int, bool] = {}

    def rollup(cat_id: int) -> tuple[MonthlyAmounts, MonthlyAmounts, bool]:
        if cat_id in monthly_cache:
            budgeted, actual = monthly_cache[cat_id]
            return budgeted, actual, has_budget_cache[cat_id]

        kids = children_of.get(cat_id, [])
        if not kids:
            budgeted = budgeted_by_category.get(cat_id, {})
            actual = actual_by_category.get(cat_id, {})
            has_budget = has_budget_by_category.get(cat_id, True)
        else:
            child_results = [rollup(kid) for kid in kids]
            budgeted = sum_monthly([r[0] for r in child_results])
            actual = sum_monthly([r[1] for r in child_results])
            has_budget = any(r[2] for r in child_results)

        monthly_cache[cat_id] = (budgeted, actual)
        has_budget_cache[cat_id] = has_budget
        return budgeted, actual, has_budget

    rows: list[ReportRow] = []

    def walk(cat_id: int, depth: int) -> None:
        cat = categories_by_id[cat_id]
        kids = children_of.get(cat_id, [])
        budgeted, actual, has_budget = rollup(cat_id)
        rows.append(
            build_row(
                cat_id,
                cat.name,
                len(kids) > 0,
                budgeted,
                actual,
                months,
                through_month,
                has_budget=has_budget,
                depth=depth,
                is_income=is_income_effective(cat_id),
            )
        )
        for kid in kids:
            walk(kid, depth + 1)

    for root_id in children_of.get(None, []):
        walk(root_id, 0)

    return rows


def get_report(db: Session, budget_id: int, year: int, through_month: int) -> list[ReportRow]:
    budget = get_budget(db, budget_id)
    leaf_ids = [bc.category_id for bc in budget.budget_categories]

    budgeted_by_category: dict[int, dict[int, Decimal]] = {}
    for bc in budget.budget_categories:
        budgeted_by_category[bc.category_id] = {
            a.month: Decimal(str(a.amount)) for a in bc.amounts if a.year == year
        }

    return _assemble_rows(db, leaf_ids, budgeted_by_category, {}, year, through_month)


def get_overview(db: Session, year: int, through_month: int) -> list[ReportRow]:
    """The Overview screen's category table: every non-archived leaf
    category, regardless of which (if any) saved budget it belongs to —
    unlike get_report, this isn't scoped to one named report.
    """
    leaves = list(
        db.execute(
            select(Category)
            .where(Category.archived_at.is_(None))
            .where(~Category.id.in_(select(Category.parent_id).where(Category.parent_id.is_not(None))))
        )
        .scalars()
        .all()
    )
    leaf_ids = [c.id for c in leaves]
    if not leaf_ids:
        return []

    amount_rows = db.execute(
        select(BudgetCategory.category_id, BudgetAmount.month, func.sum(BudgetAmount.amount))
        .join(BudgetAmount, BudgetAmount.budget_category_id == BudgetCategory.id)
        .where(BudgetCategory.category_id.in_(leaf_ids))
        .where(BudgetAmount.year == year)
        .group_by(BudgetCategory.category_id, BudgetAmount.month)
    ).all()
    budgeted_by_category: dict[int, dict[int, Decimal]] = {cid: {} for cid in leaf_ids}
    for category_id, month, total in amount_rows:
        budgeted_by_category[category_id][month] = Decimal(str(total))

    has_budget_ids = set(
        db.execute(
            select(BudgetCategory.category_id).where(BudgetCategory.category_id.in_(leaf_ids)).distinct()
        )
        .scalars()
        .all()
    )
    has_budget_by_category = {cid: cid in has_budget_ids for cid in leaf_ids}

    return _assemble_rows(db, leaf_ids, budgeted_by_category, has_budget_by_category, year, through_month)

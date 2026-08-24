from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.errors import NotFoundError, ValidationError
from app.models.account import Account
from app.models.budget import Budget, BudgetAmount, BudgetCategory
from app.models.category import Category
from app.models.split import Split
from app.models.transaction import Transaction
from app.services.budget_rollup import MonthlyAmounts, ReportRow, build_row, sum_monthly

# (category_id, account_id, {month: amount}). account_id None budgets the
# category as a whole; set, it budgets that category on that one account.
CategoryInput = tuple[int, int | None, dict[int, float]]


def _get_budget_or_404(db: Session, budget_id: int) -> Budget:
    budget = db.get(Budget, budget_id)
    if budget is None:
        raise NotFoundError(f"Budget {budget_id} not found")
    return budget


@dataclass(frozen=True)
class DroppedCategory:
    """A budget line the caller asked for that can't be kept. `name` is None
    when the category has been deleted outright."""

    category_id: int
    name: str | None
    reason: str  # "removed" | "archived" | "broken_down" | "account_removed"
    account_id: int | None = None


def _is_leaf_category(db: Session, category_id: int) -> bool:
    """Archived children don't count. The category picker hides them, so a
    category whose every child is archived renders as a selectable leaf --
    and must therefore be budgetable here, or the editor would offer a
    category that saving then silently discards."""
    child_count = db.execute(
        select(func.count())
        .select_from(Category)
        .where(Category.parent_id == category_id)
        .where(Category.archived_at.is_(None))
    ).scalar_one()
    return child_count == 0


def _partition_categories(
    db: Session, categories: list[CategoryInput]
) -> tuple[list[CategoryInput], list[DroppedCategory]]:
    """Split the submitted categories into those still budgetable and those
    that aren't any more.

    A budget outlives the category tree it was built against: a leaf that was
    budgeted last year may since have been deleted, archived, or broken down
    into subcategories. The editor can't deselect any of those -- a broken-down
    category renders as a plain section header and an archived one doesn't
    render at all -- so rejecting the save left the budget permanently
    unsaveable. Drop them instead, and report which, so the caller can say what
    happened rather than losing a line silently."""
    kept: list[CategoryInput] = []
    dropped: list[DroppedCategory] = []
    for category_id, account_id, monthly in categories:
        category = db.get(Category, category_id)
        if category is None:
            dropped.append(DroppedCategory(category_id, None, "removed", account_id))
        elif category.archived_at is not None:
            dropped.append(DroppedCategory(category_id, category.name, "archived", account_id))
        elif not _is_leaf_category(db, category_id):
            dropped.append(DroppedCategory(category_id, category.name, "broken_down", account_id))
        elif account_id is not None and db.get(Account, account_id) is None:
            # An account can be deleted out from under a per-account line the
            # same way a category can. Same treatment: drop the line, keep the
            # rest of the budget saveable.
            dropped.append(
                DroppedCategory(category_id, category.name, "account_removed", account_id)
            )
        else:
            kept.append((category_id, account_id, monthly))

    _reject_mixed_modes(db, kept)
    return kept, dropped


def _reject_mixed_modes(db: Session, categories: list[CategoryInput]) -> None:
    """A category is budgeted either as a whole or per account, never both.

    Both at once leaves "the groceries budget" ambiguous between the
    category-level line and the sum of the account lines, and no report could
    honestly pick one. Duplicate lines for the same (category, account) are
    rejected here too: SQL's unique constraint treats NULLs as distinct, so it
    won't catch two category-level lines on its own.

    Unlike a stale category this isn't something a budget drifts into -- it
    takes a caller sending a contradictory payload -- so it's an error rather
    than a silent drop."""
    accounts_by_category: dict[int, list[int | None]] = {}
    for category_id, account_id, _monthly in categories:
        accounts_by_category.setdefault(category_id, []).append(account_id)

    for category_id, account_ids in accounts_by_category.items():
        if len(account_ids) != len(set(account_ids)):
            name = _category_name(db, category_id)
            raise ValidationError(f"'{name}' has the same budget line twice")
        if None in account_ids and len(account_ids) > 1:
            name = _category_name(db, category_id)
            raise ValidationError(
                f"'{name}' is budgeted both as a whole and per account — pick one"
            )


def _category_name(db: Session, category_id: int) -> str:
    category = db.get(Category, category_id)
    return category.name if category is not None else f"#{category_id}"


def _build_budget_categories(categories: list[CategoryInput], year: int) -> list[BudgetCategory]:
    result = []
    for category_id, account_id, monthly in categories:
        bc = BudgetCategory(category_id=category_id, account_id=account_id)
        bc.amounts = [
            BudgetAmount(year=year, month=month, amount=amount) for month, amount in monthly.items()
        ]
        result.append(bc)
    return result


def create_budget(
    db: Session, name: str, categories: list[CategoryInput], year: int
) -> tuple[Budget, list[DroppedCategory]]:
    categories, dropped = _partition_categories(db, categories)
    budget = Budget(name=name)
    budget.budget_categories = _build_budget_categories(categories, year)
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return budget, dropped


def update_budget(
    db: Session,
    budget_id: int,
    name: str | None = None,
    categories: list[CategoryInput] | None = None,
    year: int | None = None,
) -> tuple[Budget, list[DroppedCategory]]:
    budget = _get_budget_or_404(db, budget_id)
    dropped: list[DroppedCategory] = []
    if name is not None:
        budget.name = name
    if categories is not None:
        if year is None:
            raise ValidationError("year is required when replacing budget categories")
        categories, dropped = _partition_categories(db, categories)
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
    return budget, dropped


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


def _actuals_by_account(
    db: Session, category_id: int, year: int, through_month: int
) -> dict[int, dict[int, Decimal]]:
    """Per-source breakdown of a category's actuals: {account_id: {month: amount}}.

    Every split hangs off a transaction with an account, so the attribution is
    already in the data -- no schema needed for this half. A categorized
    transfer attributes to the account the money *left*, since a pair carries
    its category on the withdrawal leg (transactions._category_leg)."""
    rows = db.execute(
        select(
            Transaction.account_id,
            func.strftime("%m", Transaction.date),
            func.sum(Split.amount),
        )
        .select_from(Split)
        .join(Transaction, Transaction.id == Split.transaction_id)
        .where(Split.category_id == category_id)
        .where(func.strftime("%Y", Transaction.date) == str(year))
        .group_by(Transaction.account_id, func.strftime("%m", Transaction.date))
    ).all()
    by_account: dict[int, dict[int, Decimal]] = {}
    for account_id, month_str, total in rows:
        month = int(month_str)
        if month > through_month:
            continue
        # Positive "actual spend": ledger withdrawals are negative, so negate.
        by_account.setdefault(account_id, {})[month] = -Decimal(str(total))
    return by_account


def _actuals_for_category(
    db: Session, category_id: int, year: int, through_month: int
) -> dict[int, Decimal]:
    rows = db.execute(
        select(func.strftime("%m", Transaction.date), func.sum(Split.amount))
        .select_from(Split)
        .join(Transaction, Transaction.id == Split.transaction_id)
        .where(Split.category_id == category_id)
        # No transaction-type filter. A transfer between accounts normally
        # carries no category on either leg, so it can't match category_id
        # here and stays out of every budget on its own. A transfer someone
        # deliberately categorized carries it on exactly one leg (see
        # transactions.link_as_transfer), so it counts once rather than
        # netting itself to zero across both legs.
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
    budgeted_by_account: dict[int, dict[int, MonthlyAmounts]] | None = None,
) -> list[ReportRow]:
    """Build report rows for a set of budgeted leaves plus every one of
    their ancestors, at any depth — an ancestor's budgeted/actual amounts
    are always the sum of its children (docs/requirements.md §2.2: "Parent
    category values ... are always derived"), recursively.

    `budgeted_by_account` is {category_id: {account_id: monthly}} for
    categories planned per source. Those categories get a breakdown row per
    account beneath the category row, and the category's own figures stay the
    sum of them — the same derived-parent rule, one level further down.
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

    budgeted_by_account = budgeted_by_account or {}

    actual_by_account: dict[int, dict[int, MonthlyAmounts]] = {
        cat_id: _actuals_by_account(db, cat_id, year, through_month) for cat_id in leaf_ids
    }
    # The category total is the sum of its per-account slices, so it comes from
    # the same query rather than a second one that could disagree with it.
    actual_by_category = {
        cat_id: sum_monthly(list(per_account.values()))
        for cat_id, per_account in actual_by_account.items()
    }
    # Reporting-only sign flip: deposits into an income category are positive
    # splits, which _actuals_for_category negates into a negative "actual"
    # (the convention that makes expense spend read as a positive number).
    # Negating again for income leaves undoes that, so income reads as a
    # natural positive amount received. Doesn't touch the underlying splits.
    for cat_id in leaf_ids:
        if is_income_effective(cat_id):
            actual_by_category[cat_id] = {m: -v for m, v in actual_by_category[cat_id].items()}
            actual_by_account[cat_id] = {
                account_id: {m: -v for m, v in monthly.items()}
                for account_id, monthly in actual_by_account[cat_id].items()
            }

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

    # Names for the breakdown rows, and a stable display order for them.
    breakdown_account_ids = {
        account_id
        for cat_id in leaf_ids
        for account_id in set(actual_by_account.get(cat_id, {})) | set(budgeted_by_account.get(cat_id, {}))
    }
    accounts_by_id: dict[int, Account] = {}
    if breakdown_account_ids:
        accounts_by_id = {
            a.id: a
            for a in db.execute(
                select(Account).where(Account.id.in_(breakdown_account_ids))
            ).scalars()
        }

    rows: list[ReportRow] = []

    def breakdown_rows(cat_id: int, depth: int) -> list[ReportRow]:
        """One row per source account under a leaf. Emitted when the category
        is planned per account, or when its spending came from more than one
        account and the split is worth seeing. An account that was budgeted
        but never spent on still appears (so a plan with nothing against it is
        visible), as does one spent on but never budgeted — otherwise the
        rows wouldn't add up to the category above them."""
        budgeted_lines = budgeted_by_account.get(cat_id, {})
        actual_lines = actual_by_account.get(cat_id, {})
        account_ids = set(budgeted_lines) | set(actual_lines)
        if not budgeted_lines and len(account_ids) < 2:
            return []

        # A category planned as a whole has no per-account plan to show, so
        # those rows carry actuals only and their diff reads "—".
        planned_per_account = bool(budgeted_lines)
        ordered = sorted(
            account_ids,
            key=lambda a: (accounts_by_id[a].name.lower() if a in accounts_by_id else "", a),
        )
        return [
            build_row(
                cat_id,
                accounts_by_id[account_id].name if account_id in accounts_by_id else f"#{account_id}",
                False,
                budgeted_lines.get(account_id, {}),
                actual_lines.get(account_id, {}),
                months,
                through_month,
                has_budget=planned_per_account,
                depth=depth,
                is_income=is_income_effective(cat_id),
                account_id=account_id,
            )
            for account_id in ordered
        ]

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
        if not kids:
            rows.extend(breakdown_rows(cat_id, depth + 1))
        for kid in kids:
            walk(kid, depth + 1)

    for root_id in children_of.get(None, []):
        walk(root_id, 0)

    return rows


def get_report(db: Session, budget_id: int, year: int, through_month: int) -> list[ReportRow]:
    budget = get_budget(db, budget_id)
    # A category planned per source has several lines; it's still one leaf.
    leaf_ids = list(dict.fromkeys(bc.category_id for bc in budget.budget_categories))

    budgeted_by_category: dict[int, MonthlyAmounts] = {}
    budgeted_by_account: dict[int, dict[int, MonthlyAmounts]] = {}
    for bc in budget.budget_categories:
        monthly = {a.month: Decimal(str(a.amount)) for a in bc.amounts if a.year == year}
        # The category's budgeted figure is the sum of its lines, so a
        # per-source plan rolls up exactly the way a parent category does.
        budgeted_by_category[bc.category_id] = sum_monthly(
            [budgeted_by_category.get(bc.category_id, {}), monthly]
        )
        if bc.account_id is not None:
            budgeted_by_account.setdefault(bc.category_id, {})[bc.account_id] = monthly

    return _assemble_rows(
        db,
        leaf_ids,
        budgeted_by_category,
        {},
        year,
        through_month,
        budgeted_by_account=budgeted_by_account,
    )


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

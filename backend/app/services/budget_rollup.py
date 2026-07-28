from dataclasses import dataclass, field
from decimal import Decimal

MonthlyAmounts = dict[int, Decimal]  # month (1-12) -> amount


def sum_monthly(dicts: list[MonthlyAmounts]) -> MonthlyAmounts:
    """Elementwise sum of several per-month amount dicts (used to roll a
    parent category's row up from its budgeted children)."""
    totals: MonthlyAmounts = {}
    for d in dicts:
        for month, amount in d.items():
            totals[month] = totals.get(month, Decimal(0)) + amount
    return totals


def cumulative_balance(budgeted: MonthlyAmounts, actual: MonthlyAmounts, through_month: int) -> Decimal:
    """Category balance: Σ(budgeted) − Σ(actual) from January (1) through
    `through_month` inclusive. Because this sums across the whole range
    rather than resetting each month, underspend in an earlier month
    automatically carries forward as available balance in a later one —
    "carryover" falls out of the cumulative formula for free.
    """
    budgeted_sum = sum((budgeted.get(m, Decimal(0)) for m in range(1, through_month + 1)), Decimal(0))
    actual_sum = sum((actual.get(m, Decimal(0)) for m in range(1, through_month + 1)), Decimal(0))
    return budgeted_sum - actual_sum


@dataclass
class ReportRow:
    category_id: int
    name: str
    is_parent: bool
    monthly: dict[int, tuple[Decimal, Decimal]] = field(default_factory=dict)  # month -> (budgeted, actual)
    ytd_diff: Decimal = Decimal(0)
    has_budget: bool = True
    """False when this category has no budgeted amount anywhere (e.g. an
    income category on the Overview screen) — the diff/balance is then
    meaningless and should render as "—" rather than a number."""
    depth: int = 0
    """Distance from a top-level category (0 = top level), for indenting
    arbitrarily-deep category trees in the report."""


def build_row(
    category_id: int,
    name: str,
    is_parent: bool,
    budgeted: MonthlyAmounts,
    actual: MonthlyAmounts,
    months: list[int],
    through_month: int,
    has_budget: bool = True,
    depth: int = 0,
) -> ReportRow:
    monthly = {m: (budgeted.get(m, Decimal(0)), actual.get(m, Decimal(0))) for m in months}
    ytd_diff = cumulative_balance(budgeted, actual, through_month)
    return ReportRow(
        category_id=category_id,
        name=name,
        is_parent=is_parent,
        monthly=monthly,
        ytd_diff=ytd_diff,
        has_budget=has_budget,
        depth=depth,
    )

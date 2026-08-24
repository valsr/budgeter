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
    account_id: int | None = None
    """Set on a per-source breakdown row -- the account this slice of the
    category's spending came from. None on ordinary category rows."""
    monthly: dict[int, tuple[Decimal, Decimal]] = field(default_factory=dict)  # month -> (budgeted, actual)
    ytd_diff: Decimal = Decimal(0)
    has_budget: bool = True
    """False when this category has no budgeted amount anywhere (e.g. an
    income category on the Overview screen) — the diff/balance is then
    meaningless and should render as "—" rather than a number."""
    depth: int = 0
    """Distance from a top-level category (0 = top level), for indenting
    arbitrarily-deep category trees in the report."""
    is_income: bool = False
    """Effective income flag for this category (its own Category.is_income,
    or inherited from an ancestor) — the sign flip has already been baked
    into `monthly`/`ytd_diff` above by the time this row is built; this is
    exposed purely so callers (e.g. an expense-minus-income grand total) can
    tell which rows were flipped."""

    @property
    def row_key(self) -> str:
        """Stable per-row identity for the client. category_id alone stopped
        being unique once a category can be followed by per-account rows, and
        the client uses this as both the React key and the highlight key."""
        return f"cat:{self.category_id}" + (
            "" if self.account_id is None else f":acct:{self.account_id}"
        )


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
    is_income: bool = False,
    account_id: int | None = None,
) -> ReportRow:
    monthly = {m: (budgeted.get(m, Decimal(0)), actual.get(m, Decimal(0))) for m in months}
    ytd_diff = cumulative_balance(budgeted, actual, through_month)
    return ReportRow(
        category_id=category_id,
        name=name,
        is_parent=is_parent,
        account_id=account_id,
        monthly=monthly,
        ytd_diff=ytd_diff,
        has_budget=has_budget,
        depth=depth,
        is_income=is_income,
    )

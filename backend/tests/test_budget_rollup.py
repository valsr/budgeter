from decimal import Decimal

from app.services.budget_rollup import build_row, cumulative_balance, sum_monthly


class TestCumulativeBalance:
    def test_single_month_no_carryover(self):
        budgeted = {1: Decimal("400")}
        actual = {1: Decimal("380")}
        assert cumulative_balance(budgeted, actual, through_month=1) == Decimal("20")

    def test_underspend_carries_forward(self):
        # Jan: budgeted 400, spent 300 (underspend of 100)
        # Feb: budgeted 400, spent 450 (overspend of 50)
        # cumulative balance through Feb = (400+400) - (300+450) = 800 - 750 = 50
        budgeted = {1: Decimal("400"), 2: Decimal("400")}
        actual = {1: Decimal("300"), 2: Decimal("450")}
        assert cumulative_balance(budgeted, actual, through_month=2) == Decimal("50")

    def test_overspend_reduces_future_balance(self):
        budgeted = {1: Decimal("400"), 2: Decimal("400")}
        actual = {1: Decimal("500"), 2: Decimal("400")}
        # Jan overspend of 100 eats into Feb's balance
        assert cumulative_balance(budgeted, actual, through_month=2) == Decimal("-100")

    def test_missing_months_treated_as_zero(self):
        budgeted = {1: Decimal("400")}
        actual = {}
        assert cumulative_balance(budgeted, actual, through_month=3) == Decimal("400")

    def test_through_month_truncates_later_data(self):
        budgeted = {1: Decimal("100"), 2: Decimal("100"), 3: Decimal("100")}
        actual = {1: Decimal("50"), 2: Decimal("50"), 3: Decimal("9999")}
        # month 3's huge overspend shouldn't affect a report only through month 2
        assert cumulative_balance(budgeted, actual, through_month=2) == Decimal("100")

    def test_zero_budget_and_actual(self):
        assert cumulative_balance({}, {}, through_month=6) == Decimal("0")

    def test_negative_actual_increases_balance(self):
        # a refund posted to a category (positive ledger entry -> negative "actual")
        budgeted = {1: Decimal("100")}
        actual = {1: Decimal("-20")}
        assert cumulative_balance(budgeted, actual, through_month=1) == Decimal("120")


class TestSumMonthly:
    def test_sums_across_dicts(self):
        result = sum_monthly([{1: Decimal("10"), 2: Decimal("20")}, {1: Decimal("5")}])
        assert result == {1: Decimal("15"), 2: Decimal("20")}

    def test_empty_list_returns_empty(self):
        assert sum_monthly([]) == {}

    def test_single_dict_passthrough_values(self):
        result = sum_monthly([{3: Decimal("7")}])
        assert result == {3: Decimal("7")}

    def test_dicts_with_disjoint_months(self):
        result = sum_monthly([{1: Decimal("1")}, {2: Decimal("2")}, {3: Decimal("3")}])
        assert result == {1: Decimal("1"), 2: Decimal("2"), 3: Decimal("3")}


class TestBuildRow:
    def test_row_has_cell_per_requested_month(self):
        row = build_row(
            category_id=1,
            name="groceries",
            is_parent=False,
            budgeted={1: Decimal("400"), 2: Decimal("400")},
            actual={1: Decimal("380")},
            months=[1, 2],
            through_month=2,
        )
        assert row.monthly[1] == (Decimal("400"), Decimal("380"))
        assert row.monthly[2] == (Decimal("400"), Decimal("0"))

    def test_row_ytd_diff_matches_cumulative_balance(self):
        row = build_row(
            category_id=1,
            name="groceries",
            is_parent=False,
            budgeted={1: Decimal("400"), 2: Decimal("400")},
            actual={1: Decimal("300"), 2: Decimal("450")},
            months=[1, 2],
            through_month=2,
        )
        assert row.ytd_diff == Decimal("50")

    def test_row_carries_parent_flag(self):
        row = build_row(1, "shared", True, {}, {}, [1], 1)
        assert row.is_parent is True

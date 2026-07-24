import datetime as dt
from decimal import Decimal

import pytest

from app.errors import NotFoundError, ValidationError
from app.models.account import AccountType
from app.services import accounts as accounts_svc
from app.services import budgets as budgets_svc
from app.services import categories as categories_svc
from app.services import transactions as txn_svc


@pytest.fixture()
def account(db_session):
    return accounts_svc.create_account(
        db_session, name="Main", type=AccountType.ASSET, opening_balance=1000
    )


@pytest.fixture()
def shared(db_session):
    return categories_svc.create_category(db_session, "shared")


@pytest.fixture()
def groceries(db_session, shared):
    return categories_svc.create_category(db_session, "groceries", parent_id=shared.id)


@pytest.fixture()
def utilities(db_session, shared):
    return categories_svc.create_category(db_session, "utilities", parent_id=shared.id)


def test_create_budget(db_session, groceries):
    budget = budgets_svc.create_budget(
        db_session, "Household", [(groceries.id, {1: 400, 2: 400})], year=2026
    )
    assert budget.id is not None
    assert len(budget.budget_categories) == 1
    assert len(budget.budget_categories[0].amounts) == 2


def test_create_budget_rejects_non_leaf_category(db_session, shared, groceries):
    with pytest.raises(ValidationError):
        budgets_svc.create_budget(db_session, "Bad", [(shared.id, {1: 100})], year=2026)


def test_create_budget_unknown_category_404(db_session):
    with pytest.raises(NotFoundError):
        budgets_svc.create_budget(db_session, "x", [(999, {1: 100})], year=2026)


def test_update_budget_name_only(db_session, groceries):
    budget = budgets_svc.create_budget(db_session, "Household", [(groceries.id, {1: 400})], year=2026)
    updated = budgets_svc.update_budget(db_session, budget.id, name="Renamed")
    assert updated.name == "Renamed"
    assert len(updated.budget_categories) == 1  # categories untouched


def test_update_budget_replaces_categories(db_session, groceries, utilities):
    budget = budgets_svc.create_budget(db_session, "Household", [(groceries.id, {1: 400})], year=2026)
    updated = budgets_svc.update_budget(
        db_session, budget.id, categories=[(utilities.id, {1: 180})], year=2026
    )
    assert len(updated.budget_categories) == 1
    assert updated.budget_categories[0].category_id == utilities.id


def test_update_budget_categories_without_year_rejected(db_session, groceries):
    budget = budgets_svc.create_budget(db_session, "Household", [(groceries.id, {1: 400})], year=2026)
    with pytest.raises(ValidationError):
        budgets_svc.update_budget(db_session, budget.id, categories=[(groceries.id, {1: 400})])


def test_update_budget_missing_404(db_session):
    with pytest.raises(NotFoundError):
        budgets_svc.update_budget(db_session, 999, name="x")


def test_delete_budget(db_session, groceries):
    budget = budgets_svc.create_budget(db_session, "Household", [(groceries.id, {1: 400})], year=2026)
    budgets_svc.delete_budget(db_session, budget.id)
    with pytest.raises(NotFoundError):
        budgets_svc.get_budget(db_session, budget.id)


def test_delete_budget_missing_404(db_session):
    with pytest.raises(NotFoundError):
        budgets_svc.delete_budget(db_session, 999)


def test_list_budgets(db_session, groceries):
    budgets_svc.create_budget(db_session, "A", [(groceries.id, {1: 400})], year=2026)
    budgets_svc.create_budget(db_session, "B", [(groceries.id, {1: 400})], year=2026)
    assert len(budgets_svc.list_budgets(db_session)) == 2


def test_get_budget_missing_404(db_session):
    with pytest.raises(NotFoundError):
        budgets_svc.get_budget(db_session, 999)


class TestGetReport:
    def test_report_includes_parent_rollup_and_leaf_rows(self, db_session, account, shared, groceries, utilities):
        budget = budgets_svc.create_budget(
            db_session,
            "Household",
            [(groceries.id, {1: 400, 2: 400}), (utilities.id, {1: 180, 2: 180})],
            year=2026,
        )
        txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, 5), "Costco", [(groceries.id, -380.0)]
        )
        txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 2, 3), "Hydro", [(utilities.id, -190.0)]
        )

        rows = budgets_svc.get_report(db_session, budget.id, year=2026, through_month=2)
        by_name = {r.name: r for r in rows}

        assert by_name["shared"].is_parent is True
        assert by_name["shared"].monthly[1] == (Decimal("580"), Decimal("380"))
        assert by_name["groceries"].monthly[1] == (Decimal("400"), Decimal("380"))
        assert by_name["utilities"].monthly[2] == (Decimal("180"), Decimal("190"))

        # order: parent row first, then children in category sort order
        names = [r.name for r in rows]
        assert names.index("shared") < names.index("groceries") < names.index("utilities")

    def test_report_ytd_diff_reflects_carryover(self, db_session, account, groceries):
        budget = budgets_svc.create_budget(
            db_session, "Household", [(groceries.id, {1: 400, 2: 400})], year=2026
        )
        txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, 5), "Costco", [(groceries.id, -300.0)]
        )
        txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 2, 5), "Costco", [(groceries.id, -450.0)]
        )
        rows = budgets_svc.get_report(db_session, budget.id, year=2026, through_month=2)
        groceries_row = next(r for r in rows if r.name == "groceries")
        assert groceries_row.ytd_diff == Decimal("50")  # (400+400)-(300+450)

    def test_report_excludes_transactions_outside_year(self, db_session, account, groceries):
        budget = budgets_svc.create_budget(db_session, "Household", [(groceries.id, {1: 400})], year=2026)
        txn_svc.create_transaction(
            db_session, account.id, dt.date(2025, 1, 5), "Old", [(groceries.id, -999.0)]
        )
        rows = budgets_svc.get_report(db_session, budget.id, year=2026, through_month=1)
        groceries_row = next(r for r in rows if r.name == "groceries")
        assert groceries_row.monthly[1] == (Decimal("400"), Decimal("0"))

    def test_report_excludes_months_beyond_through_month(self, db_session, account, groceries):
        budget = budgets_svc.create_budget(
            db_session, "Household", [(groceries.id, {1: 400, 3: 400})], year=2026
        )
        txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 3, 5), "Costco", [(groceries.id, -999.0)]
        )
        rows = budgets_svc.get_report(db_session, budget.id, year=2026, through_month=1)
        groceries_row = next(r for r in rows if r.name == "groceries")
        assert list(groceries_row.monthly.keys()) == [1]
        assert groceries_row.ytd_diff == Decimal("400")  # month 3 spend not counted

    def test_report_excludes_transfers(self, db_session, account, groceries):
        other = accounts_svc.create_account(
            db_session, name="Card", type=AccountType.LIABILITY, opening_balance=0
        )
        budget = budgets_svc.create_budget(db_session, "Household", [(groceries.id, {1: 400})], year=2026)
        txn_svc.create_transfer(db_session, account.id, other.id, dt.date(2026, 1, 5), "Payment", 100.0)
        rows = budgets_svc.get_report(db_session, budget.id, year=2026, through_month=1)
        groceries_row = next(r for r in rows if r.name == "groceries")
        assert groceries_row.monthly[1] == (Decimal("400"), Decimal("0"))

    def test_report_standalone_top_level_leaf_has_no_parent_row(self, db_session, account):
        top_level = categories_svc.create_category(db_session, "misc")
        budget = budgets_svc.create_budget(db_session, "Misc", [(top_level.id, {1: 50})], year=2026)
        rows = budgets_svc.get_report(db_session, budget.id, year=2026, through_month=1)
        assert len(rows) == 1
        assert rows[0].name == "misc"
        assert rows[0].is_parent is False

    def test_report_empty_budget_returns_no_rows(self, db_session):
        budget = budgets_svc.create_budget(db_session, "Empty", [], year=2026)
        assert budgets_svc.get_report(db_session, budget.id, year=2026, through_month=1) == []

    def test_report_missing_budget_404(self, db_session):
        with pytest.raises(NotFoundError):
            budgets_svc.get_report(db_session, 999, year=2026, through_month=1)

    def test_report_top_level_and_parent_rows_interleave_by_sort_order(
        self, db_session, account, shared, groceries
    ):
        # "misc" created after "shared" gets a higher sort_order, so it
        # should render after the shared group despite being a standalone leaf.
        misc = categories_svc.create_category(db_session, "misc")
        budget = budgets_svc.create_budget(
            db_session, "Mixed", [(groceries.id, {1: 100}), (misc.id, {1: 50})], year=2026
        )
        rows = budgets_svc.get_report(db_session, budget.id, year=2026, through_month=1)
        names = [r.name for r in rows]
        assert names.index("shared") < names.index("misc")

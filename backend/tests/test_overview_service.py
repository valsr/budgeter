import datetime as dt
from decimal import Decimal

import pytest

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


def test_overview_includes_all_leaf_categories_regardless_of_budget(db_session, groceries):
    income = categories_svc.create_category(db_session, "income")
    rows = budgets_svc.get_overview(db_session, year=2026, through_month=1)
    names = {r.name for r in rows}
    assert names == {"shared", "groceries", "income"}


def test_overview_category_without_any_budget_has_budget_false(db_session, groceries):
    rows = budgets_svc.get_overview(db_session, year=2026, through_month=1)
    groceries_row = next(r for r in rows if r.name == "groceries")
    assert groceries_row.has_budget is False


def test_overview_category_with_budget_has_budget_true(db_session, groceries):
    budgets_svc.create_budget(db_session, "Household", [(groceries.id, {1: 400})], year=2026)
    rows = budgets_svc.get_overview(db_session, year=2026, through_month=1)
    groceries_row = next(r for r in rows if r.name == "groceries")
    assert groceries_row.has_budget is True
    assert groceries_row.monthly[1] == (Decimal("400"), Decimal("0"))


def test_overview_parent_has_budget_true_if_any_child_budgeted(db_session, shared, groceries):
    categories_svc.create_category(db_session, "utilities", parent_id=shared.id)  # unbudgeted sibling
    budgets_svc.create_budget(db_session, "Household", [(groceries.id, {1: 400})], year=2026)
    rows = budgets_svc.get_overview(db_session, year=2026, through_month=1)
    shared_row = next(r for r in rows if r.name == "shared")
    assert shared_row.has_budget is True


def test_overview_aggregates_across_multiple_budgets_for_same_category(db_session, groceries):
    # if a category ends up in two budgets (unusual, but the API doesn't
    # forbid it), the overview should sum their amounts rather than pick one.
    budgets_svc.create_budget(db_session, "A", [(groceries.id, {1: 200})], year=2026)
    budgets_svc.create_budget(db_session, "B", [(groceries.id, {1: 100})], year=2026)
    rows = budgets_svc.get_overview(db_session, year=2026, through_month=1)
    groceries_row = next(r for r in rows if r.name == "groceries")
    assert groceries_row.monthly[1] == (Decimal("300"), Decimal("0"))


def test_overview_actual_reflects_transactions(db_session, account, groceries):
    txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 5), "Costco", [(groceries.id, -88.40)]
    )
    rows = budgets_svc.get_overview(db_session, year=2026, through_month=1)
    groceries_row = next(r for r in rows if r.name == "groceries")
    assert groceries_row.monthly[1][1] == Decimal("88.40")


def test_overview_excludes_archived_categories(db_session, groceries):
    categories_svc.archive_category(db_session, groceries.id)
    rows = budgets_svc.get_overview(db_session, year=2026, through_month=1)
    names = {r.name for r in rows}
    assert "groceries" not in names


def test_overview_no_categories_returns_empty(db_session):
    assert budgets_svc.get_overview(db_session, year=2026, through_month=1) == []


def test_overview_income_category_actual_reads_as_positive_received(db_session, account):
    salary = categories_svc.create_category(db_session, "salary", is_income=True)
    txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 5), "Payroll", [(salary.id, 2000.0)])

    rows = budgets_svc.get_overview(db_session, year=2026, through_month=1)
    salary_row = next(r for r in rows if r.name == "salary")
    assert salary_row.is_income is True
    assert salary_row.monthly[1][1] == Decimal("2000")


def test_overview_non_income_category_actual_unaffected(db_session, account, groceries):
    txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 5), "Costco", [(groceries.id, -88.40)])
    rows = budgets_svc.get_overview(db_session, year=2026, through_month=1)
    groceries_row = next(r for r in rows if r.name == "groceries")
    assert groceries_row.is_income is False
    assert groceries_row.monthly[1][1] == Decimal("88.40")


def test_overview_income_flag_inherits_from_ancestor(db_session, account):
    income = categories_svc.create_category(db_session, "income", is_income=True)
    salary = categories_svc.create_category(db_session, "salary", parent_id=income.id)
    txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 5), "Payroll", [(salary.id, 2000.0)])

    rows = budgets_svc.get_overview(db_session, year=2026, through_month=1)
    by_name = {r.name: r for r in rows}
    assert by_name["salary"].is_income is True
    assert by_name["salary"].monthly[1][1] == Decimal("2000")
    # the parent rollup sums the already-flipped child, and is itself
    # effectively income too (it inherits nothing to inherit from, but is
    # marked directly)
    assert by_name["income"].is_income is True
    assert by_name["income"].monthly[1][1] == Decimal("2000")


def test_overview_rolls_up_three_levels_deep(db_session, account, shared, groceries):
    alcohol = categories_svc.create_category(db_session, "alcohol", parent_id=groceries.id)
    txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 5), "Beer", [(alcohol.id, -40.0)])

    rows = budgets_svc.get_overview(db_session, year=2026, through_month=1)
    by_name = {r.name: r for r in rows}

    assert set(by_name) == {"shared", "groceries", "alcohol"}
    assert (by_name["shared"].depth, by_name["groceries"].depth, by_name["alcohol"].depth) == (0, 1, 2)
    assert by_name["shared"].monthly[1][1] == Decimal("40")
    assert by_name["groceries"].monthly[1][1] == Decimal("40")
    assert by_name["alcohol"].monthly[1][1] == Decimal("40")

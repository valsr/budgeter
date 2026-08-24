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
    budget, _ = budgets_svc.create_budget(
        db_session, "Household", [(groceries.id, None, {1: 400, 2: 400})], year=2026
    )
    assert budget.id is not None
    assert len(budget.budget_categories) == 1
    assert len(budget.budget_categories[0].amounts) == 2


def test_create_budget_drops_non_leaf_category(db_session, shared, groceries):
    budget, dropped = budgets_svc.create_budget(
        db_session, "Bad", [(shared.id, None, {1: 100})], year=2026
    )
    assert budget.budget_categories == []
    assert [(d.category_id, d.name, d.reason) for d in dropped] == [
        (shared.id, shared.name, "broken_down")
    ]


def test_create_budget_drops_unknown_category(db_session):
    budget, dropped = budgets_svc.create_budget(db_session, "x", [(999, None, {1: 100})], year=2026)
    assert budget.budget_categories == []
    assert [(d.category_id, d.name, d.reason) for d in dropped] == [(999, None, "removed")]


def test_update_budget_name_only(db_session, groceries):
    budget, _ = budgets_svc.create_budget(db_session, "Household", [(groceries.id, None, {1: 400})], year=2026)
    updated, _ = budgets_svc.update_budget(db_session, budget.id, name="Renamed")
    assert updated.name == "Renamed"
    assert len(updated.budget_categories) == 1  # categories untouched


def test_update_budget_replaces_categories(db_session, groceries, utilities):
    budget, _ = budgets_svc.create_budget(db_session, "Household", [(groceries.id, None, {1: 400})], year=2026)
    updated, _ = budgets_svc.update_budget(
        db_session, budget.id, categories=[(utilities.id, None, {1: 180})], year=2026
    )
    assert len(updated.budget_categories) == 1
    assert updated.budget_categories[0].category_id == utilities.id


def test_update_budget_categories_without_year_rejected(db_session, groceries):
    budget, _ = budgets_svc.create_budget(db_session, "Household", [(groceries.id, None, {1: 400})], year=2026)
    with pytest.raises(ValidationError):
        budgets_svc.update_budget(db_session, budget.id, categories=[(groceries.id, None, {1: 400})])


def test_update_budget_missing_404(db_session):
    with pytest.raises(NotFoundError):
        budgets_svc.update_budget(db_session, 999, name="x")


def test_delete_budget(db_session, groceries):
    budget, _ = budgets_svc.create_budget(db_session, "Household", [(groceries.id, None, {1: 400})], year=2026)
    budgets_svc.delete_budget(db_session, budget.id)
    with pytest.raises(NotFoundError):
        budgets_svc.get_budget(db_session, budget.id)


def test_delete_budget_missing_404(db_session):
    with pytest.raises(NotFoundError):
        budgets_svc.delete_budget(db_session, 999)


def test_list_budgets(db_session, groceries):
    budgets_svc.create_budget(db_session, "A", [(groceries.id, None, {1: 400})], year=2026)
    budgets_svc.create_budget(db_session, "B", [(groceries.id, None, {1: 400})], year=2026)
    assert len(budgets_svc.list_budgets(db_session)) == 2


def test_get_budget_missing_404(db_session):
    with pytest.raises(NotFoundError):
        budgets_svc.get_budget(db_session, 999)


class TestGetReport:
    def test_report_includes_parent_rollup_and_leaf_rows(self, db_session, account, shared, groceries, utilities):
        budget, _ = budgets_svc.create_budget(
            db_session,
            "Household",
            [(groceries.id, None, {1: 400, 2: 400}), (utilities.id, None, {1: 180, 2: 180})],
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
        budget, _ = budgets_svc.create_budget(
            db_session, "Household", [(groceries.id, None, {1: 400, 2: 400})], year=2026
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
        budget, _ = budgets_svc.create_budget(db_session, "Household", [(groceries.id, None, {1: 400})], year=2026)
        txn_svc.create_transaction(
            db_session, account.id, dt.date(2025, 1, 5), "Old", [(groceries.id, -999.0)]
        )
        rows = budgets_svc.get_report(db_session, budget.id, year=2026, through_month=1)
        groceries_row = next(r for r in rows if r.name == "groceries")
        assert groceries_row.monthly[1] == (Decimal("400"), Decimal("0"))

    def test_report_excludes_months_beyond_through_month(self, db_session, account, groceries):
        budget, _ = budgets_svc.create_budget(
            db_session, "Household", [(groceries.id, None, {1: 400, 3: 400})], year=2026
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
        budget, _ = budgets_svc.create_budget(db_session, "Household", [(groceries.id, None, {1: 400})], year=2026)
        txn_svc.create_transfer(db_session, account.id, other.id, dt.date(2026, 1, 5), "Payment", 100.0)
        rows = budgets_svc.get_report(db_session, budget.id, year=2026, through_month=1)
        groceries_row = next(r for r in rows if r.name == "groceries")
        assert groceries_row.monthly[1] == (Decimal("400"), Decimal("0"))

    def test_report_standalone_top_level_leaf_has_no_parent_row(self, db_session, account):
        top_level = categories_svc.create_category(db_session, "misc")
        budget, _ = budgets_svc.create_budget(db_session, "Misc", [(top_level.id, None, {1: 50})], year=2026)
        rows = budgets_svc.get_report(db_session, budget.id, year=2026, through_month=1)
        assert len(rows) == 1
        assert rows[0].name == "misc"
        assert rows[0].is_parent is False

    def test_report_empty_budget_returns_no_rows(self, db_session):
        budget, _ = budgets_svc.create_budget(db_session, "Empty", [], year=2026)
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
        budget, _ = budgets_svc.create_budget(
            db_session, "Mixed", [(groceries.id, None, {1: 100}), (misc.id, None, {1: 50})], year=2026
        )
        rows = budgets_svc.get_report(db_session, budget.id, year=2026, through_month=1)
        names = [r.name for r in rows]
        assert names.index("shared") < names.index("misc")

    def test_report_rolls_up_three_levels_deep(self, db_session, account, shared, groceries):
        alcohol = categories_svc.create_category(db_session, "alcohol", parent_id=groceries.id)
        budget, _ = budgets_svc.create_budget(db_session, "Household", [(alcohol.id, None, {1: 100})], year=2026)
        txn_svc.create_transaction(
            db_session, account.id, dt.date(2026, 1, 5), "Beer", [(alcohol.id, -40.0)]
        )

        rows = budgets_svc.get_report(db_session, budget.id, year=2026, through_month=1)
        by_name = {r.name: r for r in rows}

        assert set(by_name) == {"shared", "groceries", "alcohol"}
        assert by_name["shared"].depth == 0
        assert by_name["groceries"].depth == 1
        assert by_name["alcohol"].depth == 2
        assert by_name["shared"].is_parent is True
        assert by_name["groceries"].is_parent is True
        assert by_name["alcohol"].is_parent is False

        # every level's totals derive from the single leaf transaction
        for name in ("shared", "groceries", "alcohol"):
            assert by_name[name].monthly[1] == (Decimal("100"), Decimal("40"))

        names = [r.name for r in rows]
        assert names == ["shared", "groceries", "alcohol"]

    def test_report_three_levels_sums_multiple_leaves_at_each_ancestor(self, db_session, account, shared, groceries):
        alcohol = categories_svc.create_category(db_session, "alcohol", parent_id=groceries.id)
        produce = categories_svc.create_category(db_session, "produce", parent_id=groceries.id)
        budget, _ = budgets_svc.create_budget(
            db_session, "Household", [(alcohol.id, None, {1: 30}), (produce.id, None, {1: 70})], year=2026
        )
        txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 5), "Beer", [(alcohol.id, -20.0)])
        txn_svc.create_transaction(db_session, account.id, dt.date(2026, 1, 6), "Veg", [(produce.id, -60.0)])

        rows = budgets_svc.get_report(db_session, budget.id, year=2026, through_month=1)
        by_name = {r.name: r for r in rows}

        assert by_name["groceries"].monthly[1] == (Decimal("100"), Decimal("80"))  # 30+70 / 20+60
        assert by_name["shared"].monthly[1] == (Decimal("100"), Decimal("80"))  # only child is groceries
        assert by_name["alcohol"].monthly[1] == (Decimal("30"), Decimal("20"))
        assert by_name["produce"].monthly[1] == (Decimal("70"), Decimal("60"))


# --- a budget outlives the category tree it was built against ----------


def test_saving_survives_a_budgeted_category_being_broken_down(db_session, shared, groceries):
    """The reported bug: budget a leaf, later split that leaf into
    subcategories, and the budget became unsaveable -- the editor renders a
    broken-down category as a section header, so there was no way to
    deselect it and no way to save."""
    budget, _ = budgets_svc.create_budget(
        db_session, "Household", [(groceries.id, None, {1: 400})], year=2026
    )
    categories_svc.create_category(db_session, "alcohol", parent_id=groceries.id)

    updated, dropped = budgets_svc.update_budget(
        db_session, budget.id, categories=[(groceries.id, None, {1: 400})], year=2026
    )
    assert updated.budget_categories == []
    assert [(d.name, d.reason) for d in dropped] == [(groceries.name, "broken_down")]


def test_saving_keeps_the_still_valid_categories(db_session, shared, groceries, utilities):
    budget, _ = budgets_svc.create_budget(
        db_session, "Household", [(groceries.id, None, {1: 400}), (utilities.id, None, {1: 90})], year=2026
    )
    categories_svc.create_category(db_session, "alcohol", parent_id=groceries.id)

    updated, dropped = budgets_svc.update_budget(
        db_session,
        budget.id,
        categories=[(groceries.id, None, {1: 400}), (utilities.id, None, {1: 90})],
        year=2026,
    )
    assert [bc.category_id for bc in updated.budget_categories] == [utilities.id]
    assert [d.category_id for d in dropped] == [groceries.id]


def test_saving_drops_an_archived_category(db_session, shared, groceries, utilities):
    budget, _ = budgets_svc.create_budget(
        db_session, "Household", [(groceries.id, None, {1: 400}), (utilities.id, None, {1: 90})], year=2026
    )
    categories_svc.archive_category(db_session, groceries.id)

    updated, dropped = budgets_svc.update_budget(
        db_session,
        budget.id,
        categories=[(groceries.id, None, {1: 400}), (utilities.id, None, {1: 90})],
        year=2026,
    )
    assert [bc.category_id for bc in updated.budget_categories] == [utilities.id]
    assert [(d.name, d.reason) for d in dropped] == [(groceries.name, "archived")]


def test_a_category_whose_children_are_all_archived_stays_budgetable(db_session, shared, groceries):
    """The picker hides archived categories, so such a parent renders as a
    selectable leaf -- saving must not then discard it."""
    alcohol = categories_svc.create_category(db_session, "alcohol", parent_id=groceries.id)
    categories_svc.archive_category(db_session, alcohol.id)

    budget, dropped = budgets_svc.create_budget(
        db_session, "Household", [(groceries.id, None, {1: 400})], year=2026
    )
    assert dropped == []
    assert [bc.category_id for bc in budget.budget_categories] == [groceries.id]


def test_saving_reports_nothing_dropped_in_the_ordinary_case(db_session, shared, groceries):
    budget, dropped = budgets_svc.create_budget(
        db_session, "Household", [(groceries.id, None, {1: 400})], year=2026
    )
    assert dropped == []
    _, dropped = budgets_svc.update_budget(
        db_session, budget.id, categories=[(groceries.id, None, {1: 500})], year=2026
    )
    assert dropped == []


# --- budgeting a category per source account ---------------------------


@pytest.fixture()
def db_income_category(db_session):
    return categories_svc.create_category(db_session, "salary", is_income=True)


@pytest.fixture()
def card(db_session):
    return accounts_svc.create_account(
        db_session, name="Visa", type=AccountType.LIABILITY, opening_balance=0
    )


def _spend(db_session, account, category, amount, day=5):
    return txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, day), "shop", [(category.id, -amount)]
    )


def _row(rows, name, account_id=None):
    return next(r for r in rows if r.name == name and r.account_id == account_id)


def test_per_account_lines_produce_a_row_each(db_session, account, card, shared, groceries):
    budget, _ = budgets_svc.create_budget(
        db_session,
        "Household",
        [(groceries.id, account.id, {1: 250}), (groceries.id, card.id, {1: 150})],
        year=2026,
    )
    _spend(db_session, account, groceries, 240)
    _spend(db_session, card, groceries, 140.50)

    rows = budgets_svc.get_report(db_session, budget.id, year=2026, through_month=1)
    assert _row(rows, "Main", account.id).monthly[1] == (Decimal("250"), Decimal("240"))
    assert _row(rows, "Visa", card.id).monthly[1] == (Decimal("150"), Decimal("140.50"))


def test_the_category_row_is_the_sum_of_its_account_rows(db_session, account, card, shared, groceries):
    budget, _ = budgets_svc.create_budget(
        db_session,
        "Household",
        [(groceries.id, account.id, {1: 250}), (groceries.id, card.id, {1: 150})],
        year=2026,
    )
    _spend(db_session, account, groceries, 240)
    _spend(db_session, card, groceries, 140.50)

    rows = budgets_svc.get_report(db_session, budget.id, year=2026, through_month=1)
    assert _row(rows, "groceries").monthly[1] == (Decimal("400"), Decimal("380.50"))
    # ...and the parent above it still rolls up from the category.
    assert _row(rows, "shared").monthly[1] == (Decimal("400"), Decimal("380.50"))


def test_spending_on_an_unbudgeted_account_still_shows(db_session, account, card, shared, groceries):
    """Otherwise the account rows wouldn't add up to the category above them,
    and unplanned spend would vanish."""
    budget, _ = budgets_svc.create_budget(
        db_session, "Household", [(groceries.id, account.id, {1: 250})], year=2026
    )
    _spend(db_session, account, groceries, 240)
    _spend(db_session, card, groceries, 40)

    rows = budgets_svc.get_report(db_session, budget.id, year=2026, through_month=1)
    assert _row(rows, "Visa", card.id).monthly[1] == (Decimal("0"), Decimal("40"))
    assert _row(rows, "groceries").monthly[1] == (Decimal("250"), Decimal("280"))


def test_a_budgeted_account_with_no_spending_still_shows(db_session, account, card, shared, groceries):
    budget, _ = budgets_svc.create_budget(
        db_session,
        "Household",
        [(groceries.id, account.id, {1: 250}), (groceries.id, card.id, {1: 150})],
        year=2026,
    )
    _spend(db_session, account, groceries, 240)

    rows = budgets_svc.get_report(db_session, budget.id, year=2026, through_month=1)
    assert _row(rows, "Visa", card.id).monthly[1] == (Decimal("150"), Decimal("0"))


def test_a_category_level_budget_shows_no_breakdown_for_one_account(
    db_session, account, shared, groceries
):
    budget, _ = budgets_svc.create_budget(
        db_session, "Household", [(groceries.id, None, {1: 400})], year=2026
    )
    _spend(db_session, account, groceries, 240)

    rows = budgets_svc.get_report(db_session, budget.id, year=2026, through_month=1)
    assert [r for r in rows if r.account_id is not None] == []


def test_a_category_level_budget_breaks_down_when_spending_spans_accounts(
    db_session, account, card, shared, groceries
):
    """The split is worth seeing even without a per-account plan — but with no
    plan to compare against, the budgeted figure reads as unset."""
    budget, _ = budgets_svc.create_budget(
        db_session, "Household", [(groceries.id, None, {1: 400})], year=2026
    )
    _spend(db_session, account, groceries, 240)
    _spend(db_session, card, groceries, 140)

    rows = budgets_svc.get_report(db_session, budget.id, year=2026, through_month=1)
    main_row = _row(rows, "Main", account.id)
    assert main_row.monthly[1] == (Decimal("0"), Decimal("240"))
    assert main_row.has_budget is False
    assert _row(rows, "groceries").monthly[1] == (Decimal("400"), Decimal("380"))


def test_breakdown_rows_sit_directly_under_their_category(db_session, account, card, shared, groceries):
    budget, _ = budgets_svc.create_budget(
        db_session,
        "Household",
        [(groceries.id, account.id, {1: 250}), (groceries.id, card.id, {1: 150})],
        year=2026,
    )
    rows = budgets_svc.get_report(db_session, budget.id, year=2026, through_month=1)
    names = [r.name for r in rows]
    assert names == ["shared", "groceries", "Main", "Visa"]
    depths = {r.name: r.depth for r in rows}
    assert depths["Main"] == depths["groceries"] + 1


def test_row_keys_are_unique(db_session, account, card, shared, groceries):
    budget, _ = budgets_svc.create_budget(
        db_session,
        "Household",
        [(groceries.id, account.id, {1: 250}), (groceries.id, card.id, {1: 150})],
        year=2026,
    )
    rows = budgets_svc.get_report(db_session, budget.id, year=2026, through_month=1)
    keys = [r.row_key for r in rows]
    assert len(keys) == len(set(keys))


def test_mixing_category_level_and_per_account_lines_rejected(db_session, account, shared, groceries):
    with pytest.raises(ValidationError, match="pick one"):
        budgets_svc.create_budget(
            db_session,
            "Household",
            [(groceries.id, None, {1: 400}), (groceries.id, account.id, {1: 250})],
            year=2026,
        )


def test_duplicate_lines_for_the_same_account_rejected(db_session, account, shared, groceries):
    with pytest.raises(ValidationError, match="twice"):
        budgets_svc.create_budget(
            db_session,
            "Household",
            [(groceries.id, account.id, {1: 250}), (groceries.id, account.id, {1: 100})],
            year=2026,
        )


def test_a_line_naming_a_deleted_account_is_dropped(db_session, shared, groceries):
    _budget, dropped = budgets_svc.create_budget(
        db_session, "Household", [(groceries.id, 999, {1: 250})], year=2026
    )
    assert [(d.reason, d.account_id) for d in dropped] == [("account_removed", 999)]


def test_income_sign_flip_reaches_the_breakdown_rows(db_session, account, card, db_income_category):
    budget, _ = budgets_svc.create_budget(
        db_session,
        "Pay",
        [(db_income_category.id, account.id, {1: 1000})],
        year=2026,
    )
    txn_svc.create_transaction(
        db_session, account.id, dt.date(2026, 1, 5), "salary", [(db_income_category.id, 900.0)]
    )
    txn_svc.create_transaction(
        db_session, card.id, dt.date(2026, 1, 5), "bonus", [(db_income_category.id, 100.0)]
    )

    rows = budgets_svc.get_report(db_session, budget.id, year=2026, through_month=1)
    # Income reads as a natural positive amount received, on the breakdown
    # rows exactly as on the category row.
    assert _row(rows, "Main", account.id).monthly[1][1] == Decimal("900")
    assert _row(rows, "Visa", card.id).monthly[1][1] == Decimal("100")

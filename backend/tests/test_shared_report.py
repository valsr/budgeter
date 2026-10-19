from decimal import Decimal

import pytest

from app import shared_books
from app.errors import ValidationError
from app.services import shared_categories as sc
from app.services import shared_report as sr
from app.shared_models import MemberTally

MEMBERS = [(1, "alice"), (2, "bob")]


@pytest.fixture()
def sh(server_session):
    with shared_books.session_for(1) as s:
        yield s


def tally(sh, user, cat, month, amount, year=2026):
    sh.add(MemberTally(user_id=user, shared_category_id=cat.id, year=year, month=month, amount=amount))
    sh.commit()


def by_name(rows):
    return {r.name: r for r in rows}


def test_report_rolls_children_into_parent_per_member(sh):
    p = sc.create_category(sh, "Home", None, False)
    r = sc.create_category(sh, "Rent", p.id, False)
    u = sc.create_category(sh, "Utilities", p.id, False)
    sc.set_amounts(sh, 2026, [(r.id, 1, Decimal("100")), (u.id, 1, Decimal("50"))])
    tally(sh, 1, r, 1, -60)
    tally(sh, 2, r, 1, -40)
    tally(sh, 2, u, 1, -10)
    rows = sr.get_report(sh, MEMBERS, 2026, 1)
    assert [x.name for x in rows] == ["Home", "Rent", "Utilities"]
    home = rows[0]
    assert home.is_parent and home.depth == 0 and rows[1].depth == 1
    assert home.row_key == f"shared:{p.id}" and home.account_id is None
    assert home.monthly[1] == (Decimal("150"), Decimal("110"))
    assert home.ytd_diff == Decimal("40")
    alice, bob = home.members
    assert alice.monthly[1] == Decimal("60") and alice.ytd_actual == Decimal("60")
    assert bob.monthly[1] == Decimal("50") and bob.username == "bob"


def test_report_sign_convention_expense_and_inherited_income(sh):
    food = sc.create_category(sh, "Food", None, False)
    inc = sc.create_category(sh, "Income", None, True)
    sal = sc.create_category(sh, "Salary", inc.id, False)
    tally(sh, 1, food, 1, -30)
    tally(sh, 1, sal, 1, 500)
    rows = by_name(sr.get_report(sh, MEMBERS, 2026, 1))
    assert rows["Food"].monthly[1][1] == Decimal("30")
    assert rows["Salary"].monthly[1][1] == Decimal("500")
    assert rows["Salary"].is_income and rows["Income"].monthly[1][1] == Decimal("500")
    assert not rows["Food"].is_income


def test_report_ytd_diff_uses_through_month(sh):
    f = sc.create_category(sh, "Food", None, False)
    sc.set_amounts(sh, 2026, [(f.id, m, Decimal("100")) for m in (1, 2, 3)])
    tally(sh, 1, f, 1, -30)
    tally(sh, 1, f, 3, -500)
    row = sr.get_report(sh, MEMBERS, 2026, 2)[0]
    assert sorted(row.monthly) == [1, 2]
    assert row.ytd_diff == Decimal("170")
    assert row.members[0].ytd_actual == Decimal("30")
    assert row.has_budget


def test_report_lists_every_member_even_without_links(sh):
    sc.create_category(sh, "Food", None, False)
    row = sr.get_report(sh, MEMBERS, 2026, 1)[0]
    assert [(m.user_id, m.ytd_actual) for m in row.members] == [(1, 0), (2, 0)]
    assert not row.has_budget


def test_report_ignores_tallies_of_non_members(sh):
    f = sc.create_category(sh, "Food", None, False)
    tally(sh, 1, f, 1, -10)
    tally(sh, 99, f, 1, -1000)
    row = sr.get_report(sh, MEMBERS, 2026, 1)[0]
    assert row.monthly[1][1] == Decimal("10")
    assert [m.user_id for m in row.members] == [1, 2]


def test_archived_category_shown_only_with_data_in_year(sh):
    a = sc.create_category(sh, "Old", None, False)
    b = sc.create_category(sh, "Older", None, False)
    sc.update_category(sh, a.id, archived=True)
    sc.update_category(sh, b.id, archived=True)
    assert sr.get_report(sh, MEMBERS, 2026, 12) == []
    tally(sh, 1, a, 5, -5)
    assert [r.name for r in sr.get_report(sh, MEMBERS, 2026, 12)] == ["Old"]
    assert sr.get_report(sh, MEMBERS, 2025, 12) == []


def test_report_rejects_bad_through_month(sh):
    with pytest.raises(ValidationError):
        sr.get_report(sh, MEMBERS, 2026, 0)
    with pytest.raises(ValidationError):
        sr.get_report(sh, MEMBERS, 2026, 13)


def test_parent_own_tally_and_amount_added_to_children(sh):
    p = sc.create_category(sh, "Home", None, False)
    c = sc.create_category(sh, "Rent", p.id, False)
    sc.set_amounts(sh, 2026, [(p.id, 1, Decimal("20")), (c.id, 1, Decimal("100"))])
    tally(sh, 1, p, 1, -5)
    tally(sh, 1, c, 1, -60)
    rows = by_name(sr.get_report(sh, MEMBERS, 2026, 1))
    assert rows["Home"].monthly[1] == (Decimal("120"), Decimal("65"))
    assert rows["Home"].members[0].monthly[1] == Decimal("65")
    assert rows["Rent"].monthly[1] == (Decimal("100"), Decimal("60"))
    assert rows["Rent"].members[0].ytd_actual == Decimal("60")


def test_parent_only_amount_sets_has_budget_and_keeps_archived_parent(sh):
    p = sc.create_category(sh, "Home", None, False)
    sc.create_category(sh, "Rent", p.id, False)
    sc.set_amounts(sh, 2026, [(p.id, 1, Decimal("20"))])
    assert sr.get_report(sh, MEMBERS, 2026, 1)[0].has_budget
    sc.update_category(sh, p.id, archived=True)
    assert [r.name for r in sr.get_report(sh, MEMBERS, 2026, 1)][0] == "Home"

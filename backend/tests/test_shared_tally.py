from decimal import Decimal

import pytest

from app import books, server_db, shared_books
from app.errors import ValidationError
from app.models import Category, SharedCategoryLink
from app.services import shared_budgets, shared_links, shared_tally
from app.shared_models import MemberTally, SharedCategory
from tests.helpers import make_account


@pytest.fixture()
def sdb(files):
    session = server_db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _shared_categories(budget_id, *names):
    with shared_books.session_for(budget_id) as s:
        cats = [SharedCategory(name=n) for n in names]
        s.add_all(cats)
        s.commit()
        return [c.id for c in cats]


def _tallies(budget_id, user_id):
    with shared_books.session_for(budget_id) as s:
        rows = s.query(MemberTally).filter(MemberTally.user_id == user_id).all()
        return {
            (r.shared_category_id, r.year, r.month): Decimal(str(r.amount)) for r in rows
        }


def _category(client, name, parent_id=None):
    body = {"name": name}
    if parent_id is not None:
        body["parent_id"] = parent_id
    resp = client.post("/api/categories", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _txn(client, account_id, date, splits, name="Shop"):
    resp = client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "date": date,
            "name": name,
            "splits": [{"category_id": c, "amount": a} for c, a in splits],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _link(user_id, budget_id, links):
    with shared_books.session_for(budget_id) as s:
        valid = {c.id for c in s.query(SharedCategory)}
    with books.session_for(user_id) as db:
        return [
            (link.category_id, link.shared_category_id)
            for link in shared_links.set_links(db, budget_id, links, valid)
        ]


@pytest.fixture()
def alice(make_client):
    return make_client("alice")


@pytest.fixture()
def budget(sdb, alice):
    return shared_budgets.create(sdb, alice.user_id, "Home", [])


def test_compute_sums_splits_per_shared_category_and_month(alice, budget):
    a, b = _shared_categories(budget.id, "Food", "Fun")
    food, fun = _category(alice, "Groceries"), _category(alice, "Movies")
    _link(alice.user_id, budget.id, [(food, a), (fun, b)])
    acct = make_account(alice, "Checking")
    _txn(alice, acct, "2026-03-05", [(food, -12.50), (fun, -7.50)])
    assert _tallies(budget.id, alice.user_id) == {
        (a, 2026, 3): Decimal("-12.50"),
        (b, 2026, 3): Decimal("-7.50"),
    }


def test_compute_groups_by_month(alice, budget):
    (a,) = _shared_categories(budget.id, "Food")
    food = _category(alice, "Groceries")
    _link(alice.user_id, budget.id, [(food, a)])
    acct = make_account(alice, "Checking")
    _txn(alice, acct, "2026-03-05", [(food, -1)])
    _txn(alice, acct, "2026-03-25", [(food, -2)])
    _txn(alice, acct, "2026-04-01", [(food, -4)])
    assert _tallies(budget.id, alice.user_id) == {
        (a, 2026, 3): Decimal("-3"),
        (a, 2026, 4): Decimal("-4"),
    }


def test_parent_link_includes_children(alice, budget):
    (a,) = _shared_categories(budget.id, "Food")
    parent = _category(alice, "Food")
    child = _category(alice, "Groceries", parent)
    grandchild = _category(alice, "Produce", child)
    _link(alice.user_id, budget.id, [(parent, a)])
    acct = make_account(alice, "Checking")
    _txn(alice, acct, "2026-03-05", [(parent, -1), (child, -2), (grandchild, -4)])
    assert _tallies(budget.id, alice.user_id) == {(a, 2026, 3): Decimal("-7")}


def test_most_specific_link_wins(alice, budget):
    a, b = _shared_categories(budget.id, "A", "B")
    parent = _category(alice, "Food")
    child = _category(alice, "Groceries", parent)
    _link(alice.user_id, budget.id, [(parent, a), (child, b)])
    acct = make_account(alice, "Checking")
    _txn(alice, acct, "2026-03-05", [(child, -10)])
    tallies = _tallies(budget.id, alice.user_id)
    assert tallies.get((a, 2026, 3), Decimal(0)) == 0
    assert tallies[(b, 2026, 3)] == Decimal("-10")


def test_unmapped_and_uncategorised_splits_ignored(alice, budget):
    (a,) = _shared_categories(budget.id, "Food")
    food, other = _category(alice, "Groceries"), _category(alice, "Other")
    _link(alice.user_id, budget.id, [(food, a)])
    acct, savings = make_account(alice, "Checking"), make_account(alice, "Savings")
    _txn(alice, acct, "2026-03-05", [(food, -5), (other, -100), (None, -50)])
    resp = alice.post(
        "/api/transactions/transfer",
        json={"from_account_id": acct, "to_account_id": savings, "date": "2026-03-06",
              "name": "Move", "amount": 300},
    )
    assert resp.status_code == 201, resp.text
    assert _tallies(budget.id, alice.user_id) == {(a, 2026, 3): Decimal("-5")}


def test_transaction_create_edit_delete_update_the_tally(alice, budget):
    (a,) = _shared_categories(budget.id, "Food")
    food = _category(alice, "Groceries")
    _link(alice.user_id, budget.id, [(food, a)])
    acct = make_account(alice, "Checking")

    txn = _txn(alice, acct, "2026-03-05", [(food, -5)])
    assert _tallies(budget.id, alice.user_id) == {(a, 2026, 3): Decimal("-5")}

    resp = alice.patch(f"/api/transactions/{txn}", json={"date": "2026-04-02"})
    assert resp.status_code == 200, resp.text
    assert _tallies(budget.id, alice.user_id) == {(a, 2026, 4): Decimal("-5")}

    resp = alice.delete(f"/api/transactions/{txn}")
    assert resp.status_code == 204, resp.text
    assert _tallies(budget.id, alice.user_id) == {}


def test_split_edit_moves_amount_between_shared_categories(alice, budget):
    a, b = _shared_categories(budget.id, "A", "B")
    ca, cb = _category(alice, "Ca"), _category(alice, "Cb")
    _link(alice.user_id, budget.id, [(ca, a), (cb, b)])
    acct = make_account(alice, "Checking")
    txn = _txn(alice, acct, "2026-03-05", [(ca, -10)])
    resp = alice.put(
        f"/api/transactions/{txn}/splits",
        json={"splits": [{"category_id": ca, "amount": -4}, {"category_id": cb, "amount": -6}]},
    )
    assert resp.status_code == 200, resp.text
    assert _tallies(budget.id, alice.user_id) == {
        (a, 2026, 3): Decimal("-4"),
        (b, 2026, 3): Decimal("-6"),
    }


def test_reparenting_a_category_recomputes(alice, budget):
    (a,) = _shared_categories(budget.id, "Food")
    parent = _category(alice, "Food")
    loose = _category(alice, "Snacks")
    _link(alice.user_id, budget.id, [(parent, a)])
    acct = make_account(alice, "Checking")
    _txn(alice, acct, "2026-03-05", [(loose, -3)])
    assert _tallies(budget.id, alice.user_id) == {}

    resp = alice.patch(f"/api/categories/{loose}", json={"parent_id": parent})
    assert resp.status_code == 200, resp.text
    assert _tallies(budget.id, alice.user_id) == {(a, 2026, 3): Decimal("-3")}


def test_set_links_recomputes_and_validates(alice, budget):
    a, b = _shared_categories(budget.id, "A", "B")
    food = _category(alice, "Groceries")
    acct = make_account(alice, "Checking")
    _txn(alice, acct, "2026-03-05", [(food, -5)])
    assert _tallies(budget.id, alice.user_id) == {}

    links = _link(alice.user_id, budget.id, [(food, a)])
    assert links == [(food, a)]
    assert _tallies(budget.id, alice.user_id) == {(a, 2026, 3): Decimal("-5")}

    # Replacing moves it.
    _link(alice.user_id, budget.id, [(food, b)])
    assert _tallies(budget.id, alice.user_id) == {(b, 2026, 3): Decimal("-5")}

    with books.session_for(alice.user_id) as db:
        valid = {a, b}
        with pytest.raises(ValidationError):
            shared_links.set_links(db, budget.id, [(9999, a)], valid)
        with pytest.raises(ValidationError):
            shared_links.set_links(db, budget.id, [(food, a), (food, b)], valid)
        with pytest.raises(ValidationError):
            shared_links.set_links(db, budget.id, [(food, 9999)], valid)
        db.rollback()
        assert [(x.category_id, x.shared_category_id) for x in shared_links.get_links(db, budget.id)] == [
            (food, b)
        ]

    # Clearing removes the tally.
    _link(alice.user_id, budget.id, [])
    assert _tallies(budget.id, alice.user_id) == {}


def test_get_links_filters_to_valid_shared_ids(alice, budget):
    a, b = _shared_categories(budget.id, "A", "B")
    ca, cb = _category(alice, "Ca"), _category(alice, "Cb")
    _link(alice.user_id, budget.id, [(ca, a), (cb, b)])
    with books.session_for(alice.user_id) as db:
        assert len(shared_links.get_links(db, budget.id)) == 2
        assert [x.shared_category_id for x in shared_links.get_links(db, budget.id, {a})] == [a]
        assert shared_links.get_links(db, budget.id + 1) == []


def test_link_to_missing_category_is_skipped(alice, budget):
    a, b = _shared_categories(budget.id, "A", "B")
    food, gone = _category(alice, "Groceries"), _category(alice, "Gone")
    acct = make_account(alice, "Checking")
    _txn(alice, acct, "2026-03-05", [(food, -5)])
    _link(alice.user_id, budget.id, [(food, a), (gone, b)])
    # Simulate an undone category creation: the row disappears, the link stays (books have no FK
    # enforcement).
    with books.session_for(alice.user_id) as db:
        db.execute(Category.__table__.delete().where(Category.id == gone))
        db.commit()
    shared_tally.recompute_member(alice.user_id)
    assert _tallies(budget.id, alice.user_id) == {(a, 2026, 3): Decimal("-5")}


def test_recompute_rewrites_only_that_members_rows(sdb, make_client):
    alice, bob = make_client("alice"), make_client("bobby")
    budget = shared_budgets.create(sdb, alice.user_id, "Home", [bob.user_id])
    (a,) = _shared_categories(budget.id, "Food")
    fa, fb = _category(alice, "Groceries"), _category(bob, "Groceries")
    _link(alice.user_id, budget.id, [(fa, a)])
    _link(bob.user_id, budget.id, [(fb, a)])
    _txn(alice, make_account(alice, "Checking"), "2026-03-05", [(fa, -5)])
    _txn(bob, make_account(bob, "Checking"), "2026-03-05", [(fb, -7)])
    assert _tallies(budget.id, bob.user_id) == {(a, 2026, 3): Decimal("-7")}

    with shared_books.session_for(budget.id) as s:
        bob_ids = sorted(t.id for t in s.query(MemberTally).filter(MemberTally.user_id == bob.user_id))
    _txn(alice, make_account(alice, "Card"), "2026-03-06", [(fa, -1)])
    shared_tally.recompute_member(alice.user_id)
    assert _tallies(budget.id, alice.user_id) == {(a, 2026, 3): Decimal("-6")}
    assert _tallies(budget.id, bob.user_id) == {(a, 2026, 3): Decimal("-7")}
    with shared_books.session_for(budget.id) as s:
        assert sorted(t.id for t in s.query(MemberTally).filter(MemberTally.user_id == bob.user_id)) == bob_ids


def test_unrelated_commit_does_not_recompute(alice, budget, monkeypatch):
    calls = []
    monkeypatch.setattr(shared_tally, "recompute_member", calls.append)
    resp = alice.patch("/api/settings/retention", json={"retention_days": 30})
    assert resp.status_code == 200, resp.text
    assert calls == []
    # Reading through the real recompute (which opens its own books session) doesn't recurse.
    monkeypatch.undo()
    counted = []
    real = shared_tally.recompute_member

    def counting(user_id):
        counted.append(user_id)
        real(user_id)

    monkeypatch.setattr(shared_tally, "recompute_member", counting)
    _category(alice, "Groceries")
    assert counted == [alice.user_id]


def test_recompute_failure_does_not_fail_the_write(alice, budget, monkeypatch, caplog):
    (a,) = _shared_categories(budget.id, "Food")
    food = _category(alice, "Groceries")
    _link(alice.user_id, budget.id, [(food, a)])

    def boom(db, links):
        raise RuntimeError("tally exploded")

    monkeypatch.setattr(shared_tally, "compute", boom)
    acct = make_account(alice, "Checking")
    with caplog.at_level("ERROR", logger="app.services.shared_tally"):
        _txn(alice, acct, "2026-03-05", [(food, -5)])
    assert len(alice.get("/api/transactions").json()["items"]) == 1
    assert "tally exploded" in caplog.text


def test_adding_a_member_fills_their_tally(sdb, alice, budget, make_client):
    bob = make_client("bobby")
    (a,) = _shared_categories(budget.id, "Food")
    # Bob mapped and spent before joining (links are per budget id, set ahead here directly).
    fb = _category(bob, "Groceries")
    _txn(bob, make_account(bob, "Checking"), "2026-03-05", [(fb, -7)])
    with books.session_for(bob.user_id) as db:
        db.add(SharedCategoryLink(category_id=fb, shared_budget_id=budget.id, shared_category_id=a))
        db.commit()
    assert _tallies(budget.id, bob.user_id) == {}  # not a member yet: nothing to tally into

    shared_budgets.set_members(sdb, budget, [alice.user_id, bob.user_id])
    assert _tallies(budget.id, bob.user_id) == {(a, 2026, 3): Decimal("-7")}


def test_rebuild_all_restores_a_wiped_tally(alice, budget):
    (a,) = _shared_categories(budget.id, "Food")
    food = _category(alice, "Groceries")
    _link(alice.user_id, budget.id, [(food, a)])
    _txn(alice, make_account(alice, "Checking"), "2026-03-05", [(food, -5)])
    with shared_books.session_for(budget.id) as s:
        s.query(MemberTally).delete()
        s.commit()
    assert _tallies(budget.id, alice.user_id) == {}
    shared_tally.rebuild_all()
    assert _tallies(budget.id, alice.user_id) == {(a, 2026, 3): Decimal("-5")}


def test_rebuild_all_drops_tallies_of_non_members(alice, budget):
    (a,) = _shared_categories(budget.id, "Food")
    with shared_books.session_for(budget.id) as s:
        s.add(MemberTally(user_id=4242, shared_category_id=a, year=2026, month=1, amount=5))
        s.commit()
    shared_tally.rebuild_all()
    with shared_books.session_for(budget.id) as s:
        assert [t.user_id for t in s.query(MemberTally)] == []


def test_rebuild_all_continues_past_a_failing_member(sdb, make_client, monkeypatch):
    alice, bob = make_client("alice"), make_client("bobby")
    budget = shared_budgets.create(sdb, alice.user_id, "Home", [bob.user_id])
    real = shared_tally.recompute_member
    seen = []

    def flaky(user_id):
        seen.append(user_id)
        if user_id == alice.user_id:
            raise RuntimeError("nope")
        real(user_id)

    monkeypatch.setattr(shared_tally, "recompute_member", flaky)
    shared_tally.rebuild_all()
    assert sorted(seen) == sorted([alice.user_id, bob.user_id])
    assert budget.id  # still registered


def test_one_failing_budget_does_not_stop_the_others(sdb, alice, budget, monkeypatch):
    other = shared_budgets.create(sdb, alice.user_id, "Trip", [])
    (a,) = _shared_categories(budget.id, "Food")
    (b,) = _shared_categories(other.id, "Food")
    food = _category(alice, "Groceries")
    _link(alice.user_id, budget.id, [(food, a)])
    _link(alice.user_id, other.id, [(food, b)])

    # Whichever budget is visited first fails; the other must still be updated.
    first = shared_budgets.budget_ids_for_user(sdb, alice.user_id)[0]
    working = other.id if first == budget.id else budget.id
    working_shared = b if working == other.id else a
    real_session_for = shared_books.session_for

    def failing_session_for(budget_id):
        if budget_id == first:
            raise RuntimeError("unopenable")
        return real_session_for(budget_id)

    logged = []
    monkeypatch.setattr(shared_tally.shared_books, "session_for", failing_session_for)
    # A spy rather than caplog: creating the second budget ran alembic's fileConfig, which
    # resets the root logger's handlers.
    monkeypatch.setattr(shared_tally.logger, "exception", lambda *args: logged.append(args))
    _txn(alice, make_account(alice, "Checking"), "2026-03-05", [(food, -5)])
    monkeypatch.undo()

    assert _tallies(working, alice.user_id) == {(working_shared, 2026, 3): Decimal("-5")}
    assert _tallies(first, alice.user_id) == {}
    assert [args[1:] for args in logged] == [(alice.user_id, first)]

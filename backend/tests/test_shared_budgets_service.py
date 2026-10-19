import pytest

from app import shared_books
from app.errors import NotFoundError, ValidationError
from app.server_models import SharedBudget, SharedBudgetMember
from app.services import lifecycle, shared_budgets
from app.services import users as users_service
from app.shared_models import MemberTally, SharedCategory


@pytest.fixture()
def sdb(files):
    from app import server_db

    session = server_db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _user(sdb, name):
    return users_service.create_user(sdb, name, "password1")


def _seed_tally(budget_id, user_id):
    with shared_books.session_for(budget_id) as s:
        cat = SharedCategory(name="Food")
        s.add(cat)
        s.flush()
        s.add(MemberTally(user_id=user_id, shared_category_id=cat.id, year=2026, month=1, amount=5))
        s.commit()


def _tally_users(budget_id):
    with shared_books.session_for(budget_id) as s:
        return sorted(t.user_id for t in s.query(MemberTally))


def test_create_includes_creator_and_creates_file(sdb, files, monkeypatch):
    a, b = _user(sdb, "alice"), _user(sdb, "bobby")
    added = []
    monkeypatch.setattr(shared_budgets, "on_member_added", added.append)
    budget = shared_budgets.create(sdb, a.id, "  Home  ", [b.id, b.id])
    assert budget.name == "Home"
    assert sorted(shared_budgets.member_ids(budget)) == sorted([a.id, b.id])
    assert shared_books.shared_path(budget.id).exists()
    assert sorted(added) == sorted([a.id, b.id])
    assert [x.id for x in shared_budgets.list_for_user(sdb, b.id)] == [budget.id]
    assert shared_budgets.budget_ids_for_user(sdb, a.id) == [budget.id]


def test_name_validation(sdb):
    a = _user(sdb, "alice")
    with pytest.raises(ValidationError):
        shared_budgets.create(sdb, a.id, "   ", [])
    with pytest.raises(ValidationError):
        shared_budgets.create(sdb, a.id, "x" * 201, [])
    budget = shared_budgets.create(sdb, a.id, "Ok", [])
    assert shared_budgets.rename(sdb, budget, " New ").name == "New"
    with pytest.raises(ValidationError):
        shared_budgets.rename(sdb, budget, "")


def test_get_for_member_404s_for_non_member(sdb):
    a, b = _user(sdb, "alice"), _user(sdb, "bobby")
    budget = shared_budgets.create(sdb, a.id, "Home", [])
    assert shared_budgets.get_for_member(sdb, budget.id, a.id).id == budget.id
    with pytest.raises(NotFoundError):
        shared_budgets.get_for_member(sdb, budget.id, b.id)
    with pytest.raises(NotFoundError):
        shared_budgets.get_for_member(sdb, 999, a.id)


def test_set_members_rejects_empty(sdb):
    a = _user(sdb, "alice")
    budget = shared_budgets.create(sdb, a.id, "Home", [])
    with pytest.raises(ValidationError, match="at least one member"):
        shared_budgets.set_members(sdb, budget, [])


def test_set_members_rejects_disabled_new_member(sdb):
    a, b = _user(sdb, "alice"), _user(sdb, "bobby")
    users_service.update_user(sdb, b.id, is_disabled=True)
    budget = shared_budgets.create(sdb, a.id, "Home", [])
    with pytest.raises(ValidationError, match="can't be added"):
        shared_budgets.set_members(sdb, budget, [a.id, b.id])
    with pytest.raises(ValidationError, match="can't be added"):
        shared_budgets.set_members(sdb, budget, [a.id, 9999])


def test_set_members_keeps_existing_disabled_member(sdb):
    a, b = _user(sdb, "alice"), _user(sdb, "bobby")
    budget = shared_budgets.create(sdb, a.id, "Home", [b.id])
    users_service.update_user(sdb, b.id, is_disabled=True)
    shared_budgets.set_members(sdb, budget, [a.id, b.id])
    assert sorted(shared_budgets.member_ids(budget)) == sorted([a.id, b.id])


def test_removing_a_member_deletes_their_tally_rows(sdb, monkeypatch):
    a, b = _user(sdb, "alice"), _user(sdb, "bobby")
    c = _user(sdb, "carol")
    budget = shared_budgets.create(sdb, a.id, "Home", [b.id])
    _seed_tally(budget.id, b.id)
    _seed_tally(budget.id, a.id)
    added = []
    monkeypatch.setattr(shared_budgets, "on_member_added", added.append)
    shared_budgets.set_members(sdb, budget, [a.id, c.id])
    assert sorted(shared_budgets.member_ids(budget)) == sorted([a.id, c.id])
    assert _tally_users(budget.id) == [a.id]
    assert added == [c.id]


def test_delete_removes_registry_and_file(sdb):
    a = _user(sdb, "alice")
    budget = shared_budgets.create(sdb, a.id, "Home", [])
    bid = budget.id
    shared_budgets.delete(sdb, budget)
    assert sdb.get(SharedBudget, bid) is None
    assert not shared_books.shared_path(bid).exists()


def test_deleting_a_user_drops_memberships_and_last_member_budgets(sdb):
    admin, a, b = _user(sdb, "admin1"), _user(sdb, "alice"), _user(sdb, "bobby")
    shared = shared_budgets.create(sdb, a.id, "Both", [b.id])
    solo = shared_budgets.create(sdb, a.id, "Solo", [])
    _seed_tally(shared.id, a.id)
    _seed_tally(shared.id, b.id)
    shared_id, solo_id = shared.id, solo.id
    lifecycle.remove(sdb, a.id)
    sdb.expire_all()
    assert sdb.get(SharedBudget, solo_id) is None
    assert not shared_books.shared_path(solo_id).exists()
    assert sdb.get(SharedBudget, shared_id) is not None
    assert [m.user_id for m in sdb.query(SharedBudgetMember).filter_by(shared_budget_id=shared_id)] == [b.id]
    assert _tally_users(shared_id) == [b.id]


def test_directory_lists_only_enabled_users(sdb):
    b, a, c = _user(sdb, "bobby"), _user(sdb, "alice"), _user(sdb, "carol")
    users_service.update_user(sdb, c.id, is_disabled=True)
    assert [u.username for u in shared_budgets.directory(sdb)] == ["alice", "bobby"]

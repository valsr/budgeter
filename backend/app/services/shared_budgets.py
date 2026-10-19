"""The registry of shared budgets (server database) and its members. Budget data
lives in per-budget files (app/shared_books.py); everything here that takes `sdb`
works on the server database."""

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import server_db, shared_books
from app.errors import NotFoundError, ValidationError
from app.server_models import SharedBudget, SharedBudgetMember, User
from app.shared_models import MemberTally

MAX_NAME_LENGTH = 200


def _noop_member_added(user_id: int) -> None:
    pass


# Called once per user who has just become a member (including the creator), so their
# spending can be tallied into the budget. Replaced by the tally service.
on_member_added = _noop_member_added


def _clean_name(raw: str) -> str:
    name = raw.strip()
    if not name or len(name) > MAX_NAME_LENGTH:
        raise ValidationError(f"Name must be 1–{MAX_NAME_LENGTH} characters")
    return name


def list_for_user(sdb: Session, user_id: int) -> list[SharedBudget]:
    return list(
        sdb.execute(
            select(SharedBudget)
            .join(SharedBudgetMember)
            .where(SharedBudgetMember.user_id == user_id)
            .order_by(SharedBudget.name, SharedBudget.id)
        ).scalars()
    )


def budget_ids_for_user(sdb: Session, user_id: int) -> list[int]:
    return list(
        sdb.execute(
            select(SharedBudgetMember.shared_budget_id).where(SharedBudgetMember.user_id == user_id)
        ).scalars()
    )


def get_for_member(sdb: Session, budget_id: int, user_id: int) -> SharedBudget:
    budget = sdb.get(SharedBudget, budget_id)
    if budget is None or user_id not in member_ids(budget):
        raise NotFoundError(f"Shared budget {budget_id} not found")
    return budget


def member_ids(budget: SharedBudget) -> list[int]:
    return [m.user_id for m in budget.members]


def create(sdb: Session, creator_id: int, name: str, member_ids: list[int]) -> SharedBudget:
    name = _clean_name(name)
    users = sorted({creator_id, *member_ids})
    budget = SharedBudget(name=name, members=[SharedBudgetMember(user_id=u) for u in users])
    sdb.add(budget)
    sdb.commit()
    shared_books.create(budget.id)
    for user_id in users:
        on_member_added(user_id)
    return budget


def rename(sdb: Session, budget: SharedBudget, name: str) -> SharedBudget:
    budget.name = _clean_name(name)
    sdb.commit()
    return budget


def delete(sdb: Session, budget: SharedBudget) -> None:
    budget_id = budget.id
    sdb.delete(budget)
    sdb.commit()
    shared_books.delete(budget_id)


def set_members(sdb: Session, budget: SharedBudget, user_ids: list[int]) -> SharedBudget:
    wanted = set(user_ids)
    if not wanted:
        raise ValidationError("A shared budget needs at least one member")
    current = set(member_ids(budget))
    added, removed = wanted - current, current - wanted
    for user_id in sorted(added):
        user = sdb.get(User, user_id)
        if user is None or user.is_disabled:
            raise ValidationError(f"User {user_id} can't be added")

    budget.members = [m for m in budget.members if m.user_id in wanted] + [
        SharedBudgetMember(user_id=u) for u in sorted(added)
    ]
    sdb.commit()

    if removed:
        with shared_books.lock_for(budget.id), shared_books.session_for(budget.id) as session:
            session.execute(sql_delete(MemberTally).where(MemberTally.user_id.in_(removed)))
            session.commit()
    for user_id in sorted(added):
        on_member_added(user_id)
    return budget


def drop_user(budget_ids: list[int], user_id: int) -> None:
    """After a user is gone: clear their tallies from each budget they belonged to, and
    remove the files of budgets that were left with no members (their registry row went
    with the last member)."""
    with server_db.SessionLocal() as sdb:
        surviving = set(
            sdb.execute(select(SharedBudget.id).where(SharedBudget.id.in_(budget_ids))).scalars()
        )
    for budget_id in budget_ids:
        if budget_id not in surviving:
            shared_books.delete(budget_id)
            continue
        with shared_books.lock_for(budget_id), shared_books.session_for(budget_id) as session:
            session.execute(sql_delete(MemberTally).where(MemberTally.user_id == user_id))
            session.commit()


def directory(sdb: Session) -> list[User]:
    return list(
        sdb.execute(select(User).where(~User.is_disabled).order_by(User.username)).scalars()
    )

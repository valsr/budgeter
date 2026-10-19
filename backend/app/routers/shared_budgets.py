"""Shared budgets: registry in the server db, categories/amounts in each budget's own file,
and each member's category links in their own books."""

from collections.abc import Generator
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import shared_books
from app.auth import current_user
from app.db import get_db
from app.routers.budgets import row_to_read
from app.schemas.budget import MonthCell
from app.schemas.shared_budget import (
    DirectoryUserRead,
    MemberSliceRead,
    SharedAmountRead,
    SharedAmountsUpdate,
    SharedBudgetCreate,
    SharedBudgetRead,
    SharedBudgetUpdate,
    SharedCategoryCreate,
    SharedCategoryRead,
    SharedCategoryUpdate,
    SharedLinkRead,
    SharedLinksUpdate,
    SharedMembersUpdate,
    SharedReportRowRead,
)
from app.server_db import get_server_db
from app.server_models import SharedBudget, User
# Importing shared_tally is what wires shared_budgets.on_member_added to it.
from app.services import shared_budgets, shared_categories, shared_links, shared_report
from app.services import shared_tally  # noqa: F401

router = APIRouter(
    prefix="/api/shared-budgets", tags=["shared-budgets"], dependencies=[Depends(current_user)]
)
users_router = APIRouter(prefix="/api/users", tags=["shared-budgets"], dependencies=[Depends(current_user)])


def member_budget(
    budget_id: int, user: User = Depends(current_user), sdb: Session = Depends(get_server_db)
) -> SharedBudget:
    return shared_budgets.get_for_member(sdb, budget_id, user.id)


def shared_session(budget: SharedBudget = Depends(member_budget)) -> Generator[Session, None, None]:
    sh = shared_books.session_for(budget.id)
    try:
        yield sh
    finally:
        sh.close()


def _budget_read(sdb: Session, budget: SharedBudget) -> SharedBudgetRead:
    users = {
        u.id: u for u in (sdb.get(User, uid) for uid in shared_budgets.member_ids(budget)) if u
    }
    return SharedBudgetRead(
        id=budget.id,
        name=budget.name,
        members=[
            {"user_id": u.id, "username": u.username, "is_disabled": u.is_disabled}
            for u in sorted(users.values(), key=lambda u: u.username)
        ],
    )


def _category_read(c) -> SharedCategoryRead:
    return SharedCategoryRead(
        id=c.id,
        name=c.name,
        parent_id=c.parent_id,
        sort_order=c.sort_order,
        is_income=c.is_income,
        archived=c.archived_at is not None,
    )


@users_router.get("/directory", response_model=list[DirectoryUserRead])
def directory(sdb: Session = Depends(get_server_db)):
    return shared_budgets.directory(sdb)


@router.get("", response_model=list[SharedBudgetRead])
def list_budgets(user: User = Depends(current_user), sdb: Session = Depends(get_server_db)):
    return [_budget_read(sdb, b) for b in shared_budgets.list_for_user(sdb, user.id)]


@router.post("", response_model=SharedBudgetRead, status_code=201)
def create_budget(
    payload: SharedBudgetCreate,
    user: User = Depends(current_user),
    sdb: Session = Depends(get_server_db),
):
    budget = shared_budgets.create(sdb, user.id, payload.name, payload.member_ids)
    return _budget_read(sdb, budget)


@router.get("/{budget_id}", response_model=SharedBudgetRead)
def get_budget(
    budget: SharedBudget = Depends(member_budget), sdb: Session = Depends(get_server_db)
):
    return _budget_read(sdb, budget)


@router.patch("/{budget_id}", response_model=SharedBudgetRead)
def rename_budget(
    payload: SharedBudgetUpdate,
    budget: SharedBudget = Depends(member_budget),
    sdb: Session = Depends(get_server_db),
):
    return _budget_read(sdb, shared_budgets.rename(sdb, budget, payload.name))


@router.delete("/{budget_id}", status_code=204)
def delete_budget(budget: SharedBudget = Depends(member_budget), sdb: Session = Depends(get_server_db)):
    shared_budgets.delete(sdb, budget)


@router.put("/{budget_id}/members", response_model=SharedBudgetRead)
def set_members(
    payload: SharedMembersUpdate,
    budget: SharedBudget = Depends(member_budget),
    sdb: Session = Depends(get_server_db),
):
    return _budget_read(sdb, shared_budgets.set_members(sdb, budget, payload.user_ids))


@router.get("/{budget_id}/categories", response_model=list[SharedCategoryRead])
def list_categories(sh: Session = Depends(shared_session)):
    return [_category_read(c) for c in shared_categories.list_categories(sh)]


@router.post("/{budget_id}/categories", response_model=SharedCategoryRead, status_code=201)
def create_category(payload: SharedCategoryCreate, sh: Session = Depends(shared_session)):
    return _category_read(
        shared_categories.create_category(sh, payload.name, payload.parent_id, payload.is_income)
    )


@router.patch("/{budget_id}/categories/{category_id}", response_model=SharedCategoryRead)
def update_category(
    category_id: int, payload: SharedCategoryUpdate, sh: Session = Depends(shared_session)
):
    fields = payload.model_dump(exclude_unset=True)
    return _category_read(shared_categories.update_category(sh, category_id, **fields))


@router.delete("/{budget_id}/categories/{category_id}", status_code=204)
def delete_category(category_id: int, sh: Session = Depends(shared_session)):
    shared_categories.delete_category(sh, category_id)


@router.get("/{budget_id}/amounts", response_model=list[SharedAmountRead])
def get_amounts(year: int, sh: Session = Depends(shared_session)):
    return [
        SharedAmountRead(shared_category_id=a.shared_category_id, month=a.month, amount=float(a.amount))
        for a in shared_categories.get_amounts(sh, year)
    ]


@router.put("/{budget_id}/amounts", response_model=list[SharedAmountRead])
def set_amounts(payload: SharedAmountsUpdate, sh: Session = Depends(shared_session)):
    shared_categories.set_amounts(
        sh,
        payload.year,
        [
            (l.shared_category_id, l.month, None if l.amount is None else Decimal(str(l.amount)))
            for l in payload.lines
        ],
    )
    return get_amounts(payload.year, sh)


def _valid_shared_ids(sh: Session) -> set[int]:
    return {c.id for c in shared_categories.list_categories(sh)}


@router.get("/{budget_id}/links", response_model=list[SharedLinkRead])
def get_links(
    budget: SharedBudget = Depends(member_budget),
    sh: Session = Depends(shared_session),
    db: Session = Depends(get_db),
):
    links = shared_links.get_links(db, budget.id, _valid_shared_ids(sh))
    return [SharedLinkRead(category_id=l.category_id, shared_category_id=l.shared_category_id) for l in links]


@router.put("/{budget_id}/links", response_model=list[SharedLinkRead])
def set_links(
    payload: SharedLinksUpdate,
    budget: SharedBudget = Depends(member_budget),
    sh: Session = Depends(shared_session),
    db: Session = Depends(get_db),
):
    shared_links.set_links(
        db,
        budget.id,
        [(l.category_id, l.shared_category_id) for l in payload.links],
        _valid_shared_ids(sh),
    )
    # The saved ORM rows expire on commit; the response is what was asked for.
    return payload.links


@router.get("/{budget_id}/report", response_model=list[SharedReportRowRead])
def get_report(
    year: int,
    through_month: Annotated[int, Query()],
    budget: SharedBudget = Depends(member_budget),
    sdb: Session = Depends(get_server_db),
    sh: Session = Depends(shared_session),
):
    members = sorted(
        (u.id, u.username)
        for u in (sdb.get(User, uid) for uid in shared_budgets.member_ids(budget))
        if u
    )
    rows = shared_report.get_report(sh, members, year, through_month)
    out = []
    for row in rows:
        base = row_to_read(row).model_dump()
        out.append(
            SharedReportRowRead(
                **base,
                members=[
                    MemberSliceRead(
                        user_id=m.user_id,
                        username=m.username,
                        monthly={mo: float(v) for mo, v in m.monthly.items()},
                        ytd_actual=float(m.ytd_actual),
                    )
                    for m in row.members
                ],
            )
        )
    return out

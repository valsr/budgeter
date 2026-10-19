"""Member tallies: each member's actual spending in the categories they map, copied into the
shared budget's own file, so viewing a shared budget never reads anyone's books.

A tally is kept current by a hook on every books session (`install_hook`): a commit that touched
transactions, splits, categories or links recomputes that user's tallies in every shared budget
they belong to."""

import logging
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import delete, event, func, select
from sqlalchemy.orm import Session

from app import books, server_db, shared_books
from app.models import Category, SharedCategoryLink, Split, Transaction
from app.server_models import SharedBudget
from app.services import shared_budgets, shared_links
from app.shared_models import MemberTally, SharedCategory

logger = logging.getLogger(__name__)

_CENT = Decimal("0.01")
_TALLIED_TYPES = (Transaction, Split, Category, SharedCategoryLink)
_USER_KEY = "books_user_id"
_DIRTY_KEY = "shared_tally_dirty"


def compute(db: Session, links: list[tuple[int, int]]) -> dict[tuple[int, int, int], Decimal]:
    """(shared_category_id, year, month) -> summed split amounts, for `links` given as
    (category_id, shared_category_id). A link covers its category and all its descendants, except
    where a descendant has a link of its own; links to categories that no longer exist count for
    nothing."""
    parents = dict(db.execute(select(Category.id, Category.parent_id)).all())
    linked = {category_id: shared_id for category_id, shared_id in links if category_id in parents}
    if not linked:
        return {}

    mapping: dict[int, int] = {}
    for category_id in parents:
        current, seen = category_id, set()
        while current is not None and current not in seen:
            if current in linked:
                mapping[category_id] = linked[current]
                break
            seen.add(current)
            current = parents.get(current)

    year = func.strftime("%Y", Transaction.date)
    month = func.strftime("%m", Transaction.date)
    rows = db.execute(
        select(Split.category_id, year, month, func.sum(Split.amount))
        .select_from(Split)
        .join(Transaction, Transaction.id == Split.transaction_id)
        # No transaction-type filter, as in budgets._actuals_for_category: transfers carry no
        # category and so never match.
        .where(Split.category_id.in_(list(mapping)))
        .group_by(Split.category_id, year, month)
    ).all()

    totals: dict[tuple[int, int, int], Decimal] = defaultdict(Decimal)
    for category_id, year_str, month_str, total in rows:
        totals[(mapping[category_id], int(year_str), int(month_str))] += Decimal(str(total))
    return {key: value.quantize(_CENT) for key, value in totals.items()}


def _valid_shared_ids(budget_id: int) -> set[int]:
    with shared_books.session_for(budget_id) as session:
        return set(session.execute(select(SharedCategory.id)).scalars())


def _write(budget_id: int, user_id: int, totals: dict[tuple[int, int, int], Decimal]) -> None:
    with shared_books.session_for(budget_id) as session:
        session.execute(delete(MemberTally).where(MemberTally.user_id == user_id))
        session.add_all(
            MemberTally(
                user_id=user_id, shared_category_id=shared_id, year=year, month=month, amount=amount
            )
            for (shared_id, year, month), amount in totals.items()
        )
        session.commit()


def recompute_member(user_id: int) -> None:
    """Rewrite `user_id`'s tallies in every shared budget they belong to, from their books."""
    with server_db.SessionLocal() as sdb:
        budget_ids = shared_budgets.budget_ids_for_user(sdb, user_id)
    if not budget_ids:
        return
    # Read-only: this session never commits anything, so its own hook never fires.
    with books.session_for(user_id) as db:
        for budget_id in budget_ids:
            # Read the books under the lock too, so two racing recomputes can't leave the older
            # reading in place.
            with shared_books.lock_for(budget_id):
                db.rollback()  # a fresh snapshot of the books for each budget
                valid = _valid_shared_ids(budget_id)
                links = [
                    (link.category_id, link.shared_category_id)
                    for link in shared_links.get_links(db, budget_id, valid)
                ]
                _write(budget_id, user_id, compute(db, links))


def rebuild_all() -> None:
    """Recompute every member of every registered budget, and drop any tallies left behind by
    someone who is no longer a member. One user's failure doesn't stop the rest."""
    with server_db.SessionLocal() as sdb:
        budgets = {
            budget.id: set(shared_budgets.member_ids(budget))
            for budget in sdb.execute(select(SharedBudget)).scalars()
        }
    for budget_id, members in budgets.items():
        try:
            with shared_books.lock_for(budget_id), shared_books.session_for(budget_id) as session:
                session.execute(delete(MemberTally).where(MemberTally.user_id.not_in(members)))
                session.commit()
        except Exception:
            logger.exception("Couldn't clear stale tallies in shared budget %s", budget_id)
    for user_id in sorted(set().union(*budgets.values())):
        try:
            recompute_member(user_id)
        except Exception:
            logger.exception("Couldn't rebuild shared budget tallies for user %s", user_id)


def _after_flush(session: Session, flush_context) -> None:
    if session.info.get(_DIRTY_KEY):
        return
    # new/dirty/deleted still hold the pre-flush state here.
    for obj in (*session.new, *session.dirty, *session.deleted):
        if isinstance(obj, _TALLIED_TYPES):
            session.info[_DIRTY_KEY] = True
            return


def _after_commit(session: Session) -> None:
    if not session.info.pop(_DIRTY_KEY, False):
        return
    try:
        # Looked up at call time so it can be replaced (tests do).
        recompute_member(session.info[_USER_KEY])
    except Exception:
        logger.exception("Couldn't update shared budget tallies after a books commit")


def _after_rollback(session: Session) -> None:
    session.info.pop(_DIRTY_KEY, None)


def install_hook(session: Session, user_id: int) -> None:
    """Recompute `user_id`'s tallies after any commit on `session` that touched what they're
    computed from. The member's own write has already committed by then, so a failure here is
    logged, never raised.

    Only ORM unit-of-work changes are seen. No bulk update()/delete() statement on transactions,
    splits, categories or links exists today; one added later must set
    session.info["shared_tally_dirty"] itself."""
    session.info[_USER_KEY] = user_id
    event.listen(session, "after_flush", _after_flush)
    event.listen(session, "after_commit", _after_commit)
    event.listen(session, "after_rollback", _after_rollback)


shared_budgets.on_member_added = recompute_member

"""The shared budget report: the books budget report's shape, with each
member's contribution to the actuals broken out."""

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ValidationError
from app.services.budget_rollup import MonthlyAmounts, ReportRow, build_row, sum_monthly
from app.shared_models import MemberTally, SharedBudgetAmount, SharedCategory


@dataclass
class MemberSlice:
    user_id: int
    username: str
    monthly: dict[int, Decimal]
    ytd_actual: Decimal


@dataclass
class SharedReportRow(ReportRow):
    members: list[MemberSlice] = field(default_factory=list)

    @property
    def row_key(self) -> str:
        return f"shared:{self.category_id}"


def get_report(
    sh: Session, members: list[tuple[int, str]], year: int, through_month: int
) -> list[SharedReportRow]:
    if not 1 <= through_month <= 12:
        raise ValidationError("through_month must be between 1 and 12")
    months = list(range(1, through_month + 1))
    member_ids = {uid for uid, _ in members}

    cats = {c.id: c for c in sh.execute(select(SharedCategory)).scalars()}
    children_of: dict[int | None, list[int]] = {}
    for c in cats.values():
        children_of.setdefault(c.parent_id, []).append(c.id)
    for group in children_of.values():
        group.sort(key=lambda i: (cats[i].sort_order, cats[i].name))

    budget: dict[int, MonthlyAmounts] = {}
    has_amount: set[int] = set()
    for a in sh.execute(select(SharedBudgetAmount).where(SharedBudgetAmount.year == year)).scalars():
        has_amount.add(a.shared_category_id)
        if a.month <= through_month:
            budget.setdefault(a.shared_category_id, {})[a.month] = Decimal(str(a.amount))

    # Raw signed tallies, only for current members; any other user's rows are stale leftovers.
    raw: dict[int, dict[int, MonthlyAmounts]] = {}
    has_tally: set[int] = set()
    for t in sh.execute(select(MemberTally).where(MemberTally.year == year)).scalars():
        if t.user_id not in member_ids:
            continue
        has_tally.add(t.shared_category_id)
        if t.month <= through_month:
            raw.setdefault(t.shared_category_id, {}).setdefault(t.user_id, {})[t.month] = Decimal(str(t.amount))

    def effective_income(cid: int) -> bool:
        cat = cats.get(cid)
        while cat is not None:
            if cat.is_income:
                return True
            cat = cats.get(cat.parent_id) if cat.parent_id is not None else None
        return False

    has_data = has_amount | has_tally

    def visible(cid: int) -> bool:
        if cats[cid].archived_at is None or cid in has_data:
            return True
        return any(visible(k) for k in children_of.get(cid, []))

    rows: list[SharedReportRow] = []

    def rollup(cid: int):
        """(budgeted, actual, per-member actual, has_budget) for the subtree, visible kids only."""
        kids = [k for k in children_of.get(cid, []) if visible(k)]
        if not kids:
            sign = -1 if not effective_income(cid) else 1
            per_member = {
                uid: {m: sign * v for m, v in raw.get(cid, {}).get(uid, {}).items()} for uid in member_ids
            }
            return (
                budget.get(cid, {}),
                sum_monthly(list(per_member.values())),
                per_member,
                cid in has_amount,
            )
        results = [rollup(k) for k in kids]
        return (
            sum_monthly([r[0] for r in results]),
            sum_monthly([r[1] for r in results]),
            {uid: sum_monthly([r[2][uid] for r in results]) for uid in member_ids},
            any(r[3] for r in results),
        )

    def emit(cid: int, depth: int) -> None:
        cat = cats[cid]
        kids = [k for k in children_of.get(cid, []) if visible(k)]
        budgeted, actual, per_member, has_budget = rollup(cid)
        base = build_row(
            cid, cat.name, bool(kids), budgeted, actual, months, through_month,
            has_budget=has_budget, depth=depth, is_income=effective_income(cid),
        )
        slices = [
            MemberSlice(
                user_id=uid,
                username=username,
                monthly={m: per_member[uid].get(m, Decimal(0)) for m in months},
                ytd_actual=sum(per_member[uid].values(), Decimal(0)),
            )
            for uid, username in members
        ]
        rows.append(SharedReportRow(**base.__dict__, members=slices))
        for k in kids:
            emit(k, depth + 1)

    for top in children_of.get(None, []):
        if visible(top):
            emit(top, 0)
    return rows

import datetime as dt

from sqlalchemy import Select, and_, case, desc, false, func, select
from sqlalchemy.orm import Session, selectinload

from app.errors import NotFoundError, ValidationError
from app.models.account import Account
from app.models.category import Category
from app.models.change import ChangeOperation, TransactionChange
from app.models.split import Split, SuggestionSource
from app.models.transaction import Transaction, TransactionType
from app.services import change_log
from app.services.splits import validate_splits

SplitInput = tuple[int | None, float]


def _get_account_or_404(db: Session, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise NotFoundError(f"Account {account_id} not found")
    return account


def _get_transaction_or_404(db: Session, transaction_id: int) -> Transaction:
    txn = db.get(Transaction, transaction_id)
    if txn is None:
        raise NotFoundError(f"Transaction {transaction_id} not found")
    return txn


def create_transaction(
    db: Session,
    account_id: int,
    date: dt.date,
    name: str,
    splits: list[SplitInput],
) -> Transaction:
    _get_account_or_404(db, account_id)
    validate_splits(splits)

    txn = Transaction(account_id=account_id, date=date, name=name, type=TransactionType.NORMAL)
    txn.splits = [Split(category_id=cat_id, amount=amount) for cat_id, amount in splits]
    db.add(txn)
    db.commit()
    db.refresh(txn)

    after = change_log.serialize_transaction(txn)
    change_log.record_change(
        db,
        TransactionChange,
        txn.id,
        ChangeOperation.CREATE,
        before=None,
        after=after,
        summary=change_log.summarize_transaction(ChangeOperation.CREATE, None, after),
    )
    db.commit()
    return txn


def update_transaction_details(
    db: Session,
    transaction_id: int,
    date: dt.date | None = None,
    name: str | None = None,
) -> Transaction:
    txn = _get_transaction_or_404(db, transaction_id)
    before = change_log.serialize_transaction(txn)

    if date is not None:
        txn.date = date
    if name is not None:
        txn.name = name
    db.commit()
    db.refresh(txn)

    after = change_log.serialize_transaction(txn)
    if before != after:
        change_log.record_change(
            db,
            TransactionChange,
            txn.id,
            ChangeOperation.UPDATE,
            before=before,
            after=after,
            summary=change_log.summarize_transaction(ChangeOperation.UPDATE, before, after),
        )
        db.commit()
    return txn


def _transfer_pair(db: Session, txn: Transaction) -> Transaction | None:
    """The other leg of a linked transfer, or None for an orphan leg (a
    transfer whose counterpart was never linked -- see unlink_transfer)."""
    if txn.transfer_pair_id is None:
        return None
    return db.get(Transaction, txn.transfer_pair_id)


def _leg_category_id(txn: Transaction) -> int | None:
    return next((s.category_id for s in txn.splits if s.category_id is not None), None)


def _clear_category(txn: Transaction) -> None:
    for split in txn.splits:
        split.category_id = None
        split.suggested_category_id = None
        split.suggestion_source = None


def update_transaction_splits(
    db: Session, transaction_id: int, splits: list[SplitInput]
) -> Transaction:
    txn = _get_transaction_or_404(db, transaction_id)
    pair = None
    if txn.type == TransactionType.TRANSFER:
        # A transfer moves one sum of money, so it takes one category -- but
        # only one, and only on one leg. Both legs categorized would net the
        # movement to zero in every rollup (equal and opposite amounts under
        # the same category), which is the whole reason a pair carries its
        # category on a single leg.
        if len(splits) != 1:
            raise ValidationError("A transfer takes a single category, not a split across several")
        pair = _transfer_pair(db, txn)

    before = change_log.serialize_transaction(txn)
    before_pair = change_log.serialize_transaction(pair) if pair is not None else None
    current_total = sum(float(s.amount) for s in txn.splits)
    validate_splits(splits, expected_total=current_total)

    for split in list(txn.splits):
        db.delete(split)
    txn.splits = [Split(category_id=cat_id, amount=amount) for cat_id, amount in splits]
    if pair is not None and splits[0][0] is not None:
        _clear_category(pair)
    db.commit()
    db.refresh(txn)
    if pair is not None:
        db.refresh(pair)

    after = change_log.serialize_transaction(txn)
    if before != after:
        group_id = change_log.record_change(
            db,
            TransactionChange,
            txn.id,
            ChangeOperation.UPDATE,
            before=before,
            after=after,
            summary=change_log.summarize_transaction(ChangeOperation.UPDATE, before, after),
        )
        # The pair's cleared category rides in the same group, so undoing the
        # categorization restores both legs together.
        if pair is not None and before_pair != change_log.serialize_transaction(pair):
            change_log.record_change(
                db,
                TransactionChange,
                pair.id,
                ChangeOperation.UPDATE,
                before=before_pair,
                after=change_log.serialize_transaction(pair),
                summary=change_log.summarize_transaction(
                    ChangeOperation.UPDATE, before_pair, change_log.serialize_transaction(pair)
                ),
                group_id=group_id,
                is_primary=False,
            )
        db.commit()
    return txn


def delete_transaction(db: Session, transaction_id: int) -> None:
    txn = _get_transaction_or_404(db, transaction_id)
    before_txn = change_log.serialize_transaction(txn)

    pair = None
    before_pair = None
    if txn.type == TransactionType.TRANSFER and txn.transfer_pair_id is not None:
        pair = db.get(Transaction, txn.transfer_pair_id)
        if pair is not None:
            before_pair = change_log.serialize_transaction(pair)
            db.delete(pair)
    db.delete(txn)
    db.commit()

    group_id = change_log.record_change(
        db,
        TransactionChange,
        transaction_id,
        ChangeOperation.DELETE,
        before=before_txn,
        after=None,
        summary=change_log.summarize_transaction(ChangeOperation.DELETE, before_txn, None),
    )
    if pair is not None and before_pair is not None:
        change_log.record_change(
            db,
            TransactionChange,
            before_pair["id"],
            ChangeOperation.DELETE,
            before=before_pair,
            after=None,
            summary=change_log.summarize_transaction(ChangeOperation.DELETE, before_pair, None),
            group_id=group_id,
            is_primary=False,
        )
    db.commit()


def create_transfer(
    db: Session,
    from_account_id: int,
    to_account_id: int,
    date: dt.date,
    name: str,
    amount: float,
) -> tuple[Transaction, Transaction]:
    if from_account_id == to_account_id:
        raise ValidationError("Transfer must be between two different accounts")
    if amount <= 0:
        raise ValidationError("Transfer amount must be positive")

    _get_account_or_404(db, from_account_id)
    _get_account_or_404(db, to_account_id)

    from_txn = Transaction(
        account_id=from_account_id, date=date, name=name, type=TransactionType.TRANSFER
    )
    from_txn.splits = [Split(category_id=None, amount=-amount)]
    db.add(from_txn)
    db.flush()

    to_txn = Transaction(
        account_id=to_account_id,
        date=date,
        name=name,
        type=TransactionType.TRANSFER,
        transfer_pair_id=from_txn.id,
    )
    to_txn.splits = [Split(category_id=None, amount=amount)]
    db.add(to_txn)
    db.flush()

    from_txn.transfer_pair_id = to_txn.id
    db.commit()
    db.refresh(from_txn)
    db.refresh(to_txn)

    transfer_summary = f"Created transfer '{name}' (${amount:.2f})"
    after_from = change_log.serialize_transaction(from_txn)
    after_to = change_log.serialize_transaction(to_txn)
    group_id = change_log.record_change(
        db,
        TransactionChange,
        from_txn.id,
        ChangeOperation.CREATE,
        before=None,
        after=after_from,
        summary=transfer_summary,
    )
    change_log.record_change(
        db,
        TransactionChange,
        to_txn.id,
        ChangeOperation.CREATE,
        before=None,
        after=after_to,
        summary=transfer_summary,
        group_id=group_id,
        is_primary=False,
    )
    db.commit()
    return from_txn, to_txn


TRANSFER_DAY_WINDOW = 5


def _single_split_amount(txn: Transaction) -> float:
    """The signed amount of a transaction that can take part in a transfer.
    A transfer is one movement of money, so each leg must be a single split —
    a transaction split across categories has no single amount to match on."""
    if len(txn.splits) != 1:
        return 0.0
    return float(txn.splits[0].amount)


def find_transfer_candidates(
    db: Session, transaction_id: int, day_window: int = TRANSFER_DAY_WINDOW
) -> list[Transaction]:
    """Transactions that could be the other leg of `transaction_id`: a normal,
    single-split transaction on a *different* account whose amount is the exact
    negation of this one, dated within `day_window` days either side.

    Ordered by date proximity so the likeliest match sorts first — banks post
    the two legs a day or two apart at least as often as on the same day."""
    txn = _get_transaction_or_404(db, transaction_id)
    if txn.type != TransactionType.NORMAL:
        raise ValidationError("Only normal transactions can be linked as a transfer")
    amount = _single_split_amount(txn)
    if amount == 0:
        raise ValidationError("Only single-split, non-zero transactions can be linked as a transfer")

    split_count = (
        select(func.count(Split.id))
        .where(Split.transaction_id == Transaction.id)
        .correlate(Transaction)
        .scalar_subquery()
    )
    candidate_total = (
        select(func.sum(Split.amount))
        .where(Split.transaction_id == Transaction.id)
        .correlate(Transaction)
        .scalar_subquery()
    )
    stmt = (
        select(Transaction)
        .options(selectinload(Transaction.splits))
        .where(Transaction.id != txn.id)
        .where(Transaction.type == TransactionType.NORMAL)
        .where(Transaction.account_id != txn.account_id)
        .where(Transaction.date >= txn.date - dt.timedelta(days=day_window))
        .where(Transaction.date <= txn.date + dt.timedelta(days=day_window))
        .where(split_count == 1)
        .where(candidate_total == -amount)
    )
    candidates = list(db.execute(stmt).scalars().unique().all())
    candidates.sort(key=lambda c: (abs((c.date - txn.date).days), c.date, c.id))
    return candidates


def link_as_transfer(
    db: Session, transaction_id: int, other_transaction_id: int
) -> tuple[Transaction, Transaction]:
    """Mark two existing transactions as the two legs of one transfer.

    Needed when both legs were imported independently — each account's own
    statement carries one side — so neither came from create_transfer.

    `transaction_id` is the leg the user acted on, and that decides which leg
    carries the pair's category: a linked pair holds its category on exactly
    one leg (both legs would net the movement to zero under that category),
    and which leg it is sets the sign the category sees. Categorizing the
    withdrawal leg reads as money leaving that account *into* the category;
    categorizing the deposit leg credits the category instead."""
    if transaction_id == other_transaction_id:
        raise ValidationError("A transaction can't be linked to itself")

    txn = _get_transaction_or_404(db, transaction_id)
    other = _get_transaction_or_404(db, other_transaction_id)

    for leg in (txn, other):
        if leg.type != TransactionType.NORMAL:
            raise ValidationError(f"'{leg.name}' is already part of a transfer")
        if len(leg.splits) != 1:
            raise ValidationError(f"'{leg.name}' is split across categories — remove the split first")
    if txn.account_id == other.account_id:
        raise ValidationError("A transfer must be between two different accounts")

    amount = _single_split_amount(txn)
    if amount == 0:
        raise ValidationError("Transfer amount must be non-zero")
    if _single_split_amount(other) != -amount:
        raise ValidationError("The two legs must be equal and opposite amounts")

    before_txn = change_log.serialize_transaction(txn)
    before_other = change_log.serialize_transaction(other)

    # At most one leg may carry a category. Linking is non-destructive where
    # it can be: if only `other` was categorized, its category stays put --
    # moving it onto the selected leg would silently flip the sign it
    # contributes. If both were, the selected leg wins and the other is
    # reported as dropped rather than silently binned.
    dropped_category_id = None
    if _leg_category_id(txn) is not None and _leg_category_id(other) is not None:
        dropped_category_id = _leg_category_id(other)
        _clear_category(other)

    for leg, pair in ((txn, other), (other, txn)):
        leg.type = TransactionType.TRANSFER
        leg.transfer_pair_id = pair.id
    db.commit()
    db.refresh(txn)
    db.refresh(other)

    summary = f"Linked '{txn.name}' and '{other.name}' as a transfer (${abs(amount):.2f})"
    if dropped_category_id is not None:
        category = db.get(Category, dropped_category_id)
        label = category.name if category is not None else f"#{dropped_category_id}"
        summary += f"; dropped '{label}' from '{other.name}' (a transfer is categorized on one leg)"
    group_id = change_log.record_change(
        db,
        TransactionChange,
        txn.id,
        ChangeOperation.UPDATE,
        before=before_txn,
        after=change_log.serialize_transaction(txn),
        summary=summary,
    )
    change_log.record_change(
        db,
        TransactionChange,
        other.id,
        ChangeOperation.UPDATE,
        before=before_other,
        after=change_log.serialize_transaction(other),
        summary=summary,
        group_id=group_id,
        is_primary=False,
    )
    db.commit()
    return txn, other


def unlink_transfer(db: Session, transaction_id: int) -> list[Transaction]:
    """Turn a transfer back into ordinary transactions on both accounts.

    The reverse of link_as_transfer. Unlike delete_transaction it keeps both
    rows — the money did move, only the pairing was wrong — so the legs come
    back uncategorized and available for categorization again."""
    txn = _get_transaction_or_404(db, transaction_id)
    if txn.type != TransactionType.TRANSFER:
        raise ValidationError("This transaction is not a transfer")

    pair = db.get(Transaction, txn.transfer_pair_id) if txn.transfer_pair_id is not None else None
    legs = [txn] if pair is None else [txn, pair]
    befores = [change_log.serialize_transaction(leg) for leg in legs]

    for leg in legs:
        leg.type = TransactionType.NORMAL
        leg.transfer_pair_id = None
    db.commit()
    for leg in legs:
        db.refresh(leg)

    summary = f"Unlinked transfer '{txn.name}'"
    group_id = None
    for leg, before in zip(legs, befores):
        group_id = change_log.record_change(
            db,
            TransactionChange,
            leg.id,
            ChangeOperation.UPDATE,
            before=before,
            after=change_log.serialize_transaction(leg),
            summary=summary,
            group_id=group_id,
            is_primary=group_id is None,
        )
    db.commit()
    return legs


def get_transaction(db: Session, transaction_id: int) -> Transaction:
    return _get_transaction_or_404(db, transaction_id)


def _get_split_or_404(db: Session, transaction_id: int, split_id: int) -> Split:
    txn = _get_transaction_or_404(db, transaction_id)
    split = next((s for s in txn.splits if s.id == split_id), None)
    if split is None:
        raise NotFoundError(f"Split {split_id} not found on transaction {transaction_id}")
    return split


def _record_split_change(db: Session, txn: Transaction, before: dict) -> None:
    after = change_log.serialize_transaction(txn)
    if before != after:
        change_log.record_change(
            db,
            TransactionChange,
            txn.id,
            ChangeOperation.UPDATE,
            before=before,
            after=after,
            summary=change_log.summarize_transaction(ChangeOperation.UPDATE, before, after),
        )
        db.commit()


def accept_suggestion(db: Session, transaction_id: int, split_id: int) -> Split:
    split = _get_split_or_404(db, transaction_id, split_id)
    if split.suggested_category_id is None:
        raise ValidationError("This split has no pending suggestion to accept")
    txn = split.transaction
    before = change_log.serialize_transaction(txn)
    split.category_id = split.suggested_category_id
    split.suggested_category_id = None
    split.suggestion_source = None
    db.commit()
    db.refresh(split)
    db.refresh(txn)
    _record_split_change(db, txn, before)
    return split


def reject_suggestion(db: Session, transaction_id: int, split_id: int) -> Split:
    split = _get_split_or_404(db, transaction_id, split_id)
    if split.suggested_category_id is None:
        raise ValidationError("This split has no pending suggestion to reject")
    txn = split.transaction
    before = change_log.serialize_transaction(txn)
    split.suggested_category_id = None
    split.suggestion_source = None
    db.commit()
    db.refresh(split)
    db.refresh(txn)
    _record_split_change(db, txn, before)
    return split


def _descendant_category_ids(db: Session, category_id: int) -> list[int]:
    """category_id plus every descendant at any depth — categories can be
    nested arbitrarily deep, so filtering by a parent must include the
    whole subtree, not just direct children."""
    ids = [category_id]
    frontier = [category_id]
    while frontier:
        children = db.execute(select(Category.id).where(Category.parent_id == frontier.pop())).scalars().all()
        ids.extend(children)
        frontier.extend(children)
    return ids


def _is_uncategorized_clause():
    """A transaction is "uncategorized" when it has a split lacking a
    confirmed category and nothing else in its entry supplies one.

    Transfers are included. They used to be excluded as categorized-by-
    definition, which was right while a transfer *couldn't* carry a category
    -- but a linked pair now takes one (see link_as_transfer), so a pair
    with none is genuinely outstanding work and belongs in the filter.

    The pair check is what keeps a *categorized* pair out: its category sits
    on one leg by design, so the other leg's NULL split is not a missing
    categorization, it's the model working."""
    uncat_split_exists = (
        select(Split.id)
        .where(Split.transaction_id == Transaction.id)
        .where(Split.category_id.is_(None))
        # Correlate Transaction only. An amount or category filter joins Split
        # into the outer query too, and without this SQLAlchemy auto-correlates
        # that away as well -- leaving this subquery with no FROM at all and
        # raising rather than running.
        .correlate(Transaction)
        .exists()
    )
    # Matches nothing when transfer_pair_id is NULL, so an ordinary
    # transaction reduces to the plain "has an uncategorized split" test.
    pair_carries_category = (
        select(Split.id)
        .where(Split.transaction_id == Transaction.transfer_pair_id)
        .where(Split.category_id.is_not(None))
        .correlate(Transaction)
        .exists()
    )
    return and_(uncat_split_exists, ~pair_carries_category)


def _entry_key_expr():
    """The id of the "entry" a transaction row belongs to. A linked transfer's
    two legs share one key -- the lower of the two ids -- so grouping by this
    collapses a pair into a single entry; every other transaction is its own
    entry."""
    return case(
        (Transaction.transfer_pair_id.is_(None), Transaction.id),
        else_=func.min(Transaction.id, Transaction.transfer_pair_id),
    )


def _entry_key(txn: Transaction) -> int:
    """The Python-side twin of _entry_key_expr, for ordering already-fetched
    rows -- keep the two in step."""
    if txn.transfer_pair_id is None:
        return txn.id
    return min(txn.id, txn.transfer_pair_id)


def _base_query(
    account_id: int | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    name_contains: str | None = None,
    category_ids: list[int] | None = None,
    show_categorized: bool = True,
    show_uncategorized: bool = True,
) -> Select:
    stmt = select(Transaction).options(selectinload(Transaction.splits))
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    if date_from is not None:
        stmt = stmt.where(Transaction.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Transaction.date <= date_to)
    if name_contains:
        stmt = stmt.where(Transaction.name.ilike(f"%{name_contains}%"))
    if not show_categorized and not show_uncategorized:
        stmt = stmt.where(false())
    elif not show_categorized:
        stmt = stmt.where(_is_uncategorized_clause())
    elif not show_uncategorized:
        stmt = stmt.where(~_is_uncategorized_clause())
    if amount_min is not None or amount_max is not None or category_ids is not None:
        stmt = stmt.join(Split, Split.transaction_id == Transaction.id)
        if amount_min is not None:
            stmt = stmt.where(Split.amount >= amount_min)
        if amount_max is not None:
            stmt = stmt.where(Split.amount <= amount_max)
        if category_ids is not None:
            stmt = stmt.where(Split.category_id.in_(category_ids))
    return stmt.distinct()


def list_transactions(
    db: Session,
    account_id: int | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    name_contains: str | None = None,
    category_id: int | None = None,
    page: int = 1,
    page_size: int = 100,
    show_categorized: bool = True,
    show_uncategorized: bool = True,
) -> tuple[list[Transaction], int]:
    category_ids = _descendant_category_ids(db, category_id) if category_id is not None else None

    stmt = _base_query(
        account_id,
        date_from,
        date_to,
        amount_min,
        amount_max,
        name_contains,
        category_ids,
        show_categorized,
        show_uncategorized,
    )
    # Page by *entry*, not by row: a linked transfer is one movement of money
    # shown as one line, so its two legs must count once toward the page size
    # and never straddle a page boundary. Both legs are always returned
    # together, even when the filters matched only one of them -- rendering
    # the collapsed line needs the other leg's account and amount.
    matching_ids = stmt.with_only_columns(Transaction.id).distinct().subquery()
    key = _entry_key_expr()
    entry_rows = (
        select(
            key.label("entry_key"),
            func.max(Transaction.date).label("entry_date"),
            func.max(Transaction.id).label("entry_id"),
        )
        .where(Transaction.id.in_(select(matching_ids.c.id)))
        .group_by(key)
    )
    total = db.execute(select(func.count()).select_from(entry_rows.subquery())).scalar_one()

    page_keys = list(
        db.execute(
            entry_rows.order_by(desc("entry_date"), desc("entry_id"))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    if not page_keys:
        return [], total

    items = list(
        db.execute(
            select(Transaction).options(selectinload(Transaction.splits)).where(key.in_(page_keys))
        )
        .scalars()
        .unique()
        .all()
    )
    # Restore the page's ordering, which the fetch-by-key above doesn't carry,
    # and keep a pair's legs adjacent.
    key_order = {k: i for i, k in enumerate(page_keys)}
    items.sort(key=lambda t: (key_order[_entry_key(t)], t.id))
    return items, total


def count_uncategorized(db: Session) -> int:
    """Counted by entry, matching the list: a linked pair is one thing to
    categorize, not two."""
    stmt = (
        select(func.count(func.distinct(_entry_key_expr())))
        .select_from(Transaction)
        .where(_is_uncategorized_clause())
    )
    return db.execute(stmt).scalar_one()


# --- undo-only helpers -------------------------------------------------
#
# Used exclusively by app/services/undo.py. apply_transaction_snapshot
# replaces date/name/splits wholesale (including suggested_category_id/
# suggestion_source, which none of update_transaction_details /
# update_transaction_splits / accept_suggestion / reject_suggestion alone
# can fully restore) so a single call can reverse an UPDATE row regardless
# of which of those four originally produced it. restore_transaction
# recreates a deleted transaction (and its splits) with the original id;
# undoing a create reuses delete_transaction as-is, since it already
# handles the transfer-pair cascade.


def apply_transaction_snapshot(db: Session, transaction_id: int, snapshot: dict) -> Transaction:
    txn = _get_transaction_or_404(db, transaction_id)
    before = change_log.serialize_transaction(txn)

    txn.date = dt.date.fromisoformat(snapshot["date"])
    txn.name = snapshot["name"]
    # type/transfer_pair_id are restored too — link_as_transfer and
    # unlink_transfer log UPDATEs that change nothing else, so an undo that
    # skipped these fields would be a no-op for them.
    txn.type = TransactionType(snapshot["type"])
    txn.transfer_pair_id = snapshot["transfer_pair_id"]
    for split in list(txn.splits):
        db.delete(split)
    txn.splits = [
        Split(
            category_id=s["category_id"],
            amount=s["amount"],
            suggested_category_id=s["suggested_category_id"],
            suggestion_source=SuggestionSource(s["suggestion_source"]) if s["suggestion_source"] else None,
        )
        for s in snapshot["splits"]
    ]
    db.commit()
    db.refresh(txn)

    after = change_log.serialize_transaction(txn)
    if before != after:
        change_log.record_change(
            db,
            TransactionChange,
            txn.id,
            ChangeOperation.UPDATE,
            before=before,
            after=after,
            summary=change_log.summarize_transaction(ChangeOperation.UPDATE, before, after),
        )
        db.commit()
    return txn


def restore_transaction(db: Session, snapshot: dict) -> Transaction:
    if db.get(Transaction, snapshot["id"]) is not None:
        raise ValidationError(f"Can't undo: transaction id {snapshot['id']} is now in use by a different record")

    txn = Transaction(
        id=snapshot["id"],
        account_id=snapshot["account_id"],
        date=dt.date.fromisoformat(snapshot["date"]),
        name=snapshot["name"],
        type=TransactionType(snapshot["type"]),
        transfer_pair_id=snapshot["transfer_pair_id"],
    )
    txn.splits = [
        Split(
            category_id=s["category_id"],
            amount=s["amount"],
            suggested_category_id=s["suggested_category_id"],
            suggestion_source=SuggestionSource(s["suggestion_source"]) if s["suggestion_source"] else None,
        )
        for s in snapshot["splits"]
    ]
    db.add(txn)
    db.commit()
    db.refresh(txn)

    after = change_log.serialize_transaction(txn)
    change_log.record_change(
        db,
        TransactionChange,
        txn.id,
        ChangeOperation.CREATE,
        before=None,
        after=after,
        summary=change_log.summarize_transaction(ChangeOperation.CREATE, None, after),
    )
    db.commit()
    return txn

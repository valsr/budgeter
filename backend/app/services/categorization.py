from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import books
from app.models.split import Split, SuggestionSource
from app.models.transaction import Transaction, TransactionType
from app.services.rule_engine import TransactionContext, find_matching_rule
from app.services.rules import list_rules, rules_to_specs


def find_uncategorized_split(txn: Transaction) -> Split | None:
    """The transaction's sole still-uncategorized split, if there is exactly one."""
    uncategorized = [s for s in txn.splits if s.category_id is None]
    return uncategorized[0] if len(uncategorized) == 1 else None


def list_eligible_for_suggestion(db: Session, transaction_ids: list[int] | None = None) -> list[Transaction]:
    """Normal (non-transfer) transactions with exactly one still-uncategorized
    split — see find_uncategorized_split for why "exactly one"."""
    stmt = (
        select(Transaction)
        .options(selectinload(Transaction.splits))
        .where(Transaction.type == TransactionType.NORMAL)
    )
    if transaction_ids is not None:
        stmt = stmt.where(Transaction.id.in_(transaction_ids))

    transactions = db.execute(stmt).scalars().unique().all()
    return [t for t in transactions if find_uncategorized_split(t) is not None]


def run_categorization(db: Session, transaction_ids: list[int] | None = None) -> int:
    """Apply rule-based categorization to uncategorized transactions."""
    rules = rules_to_specs(list_rules(db))
    if not rules:
        return 0

    transactions = list_eligible_for_suggestion(db, transaction_ids)

    suggested_count = 0
    for txn in transactions:
        split = find_uncategorized_split(txn)

        ctx = TransactionContext(
            date=txn.date, name=txn.name, account_id=txn.account_id, amount=float(split.amount)
        )
        match = find_matching_rule(rules, ctx)
        if match is None:
            continue

        split.suggested_category_id = match.target_category_id
        split.suggestion_source = SuggestionSource.RULE
        suggested_count += 1

    db.commit()
    return suggested_count


def run_categorization_in_background(user_id: int, transaction_ids: list[int] | None = None) -> int:
    """Entry point for FastAPI's BackgroundTasks (see routers/imports.py)."""
    session = books.session_for(user_id)
    try:
        return run_categorization(session, transaction_ids)
    finally:
        session.close()

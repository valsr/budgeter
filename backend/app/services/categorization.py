from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.split import SuggestionSource
from app.models.transaction import Transaction, TransactionType
from app.services.rule_engine import TransactionContext, find_matching_rule
from app.services.rules import list_rules, rules_to_specs


def _uncategorized_transactions_query(transaction_ids: list[int] | None):
    stmt = (
        select(Transaction)
        .options(selectinload(Transaction.splits))
        .where(Transaction.type == TransactionType.NORMAL)
    )
    if transaction_ids is not None:
        stmt = stmt.where(Transaction.id.in_(transaction_ids))
    return stmt


def run_categorization(db: Session, transaction_ids: list[int] | None = None) -> int:
    """Apply rule-based categorization to uncategorized transactions.

    Only transactions with a single, still-uncategorized split are
    eligible — a rule proposes one category for the transaction as a
    whole, and once a split's category_id is set it is considered
    confirmed and is never touched here (docs/requirements.md §3.1).
    `transaction_ids=None` means "all eligible transactions" (used right
    after import, and whenever a rule is created/edited); a specific list
    scopes this to a manual/bulk re-run selection.

    Returns the number of transactions that received a new suggestion.
    """
    rules = rules_to_specs(list_rules(db))
    if not rules:
        return 0

    transactions = db.execute(_uncategorized_transactions_query(transaction_ids)).scalars().unique().all()

    suggested_count = 0
    for txn in transactions:
        if len(txn.splits) != 1 or txn.splits[0].category_id is not None:
            continue
        split = txn.splits[0]

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

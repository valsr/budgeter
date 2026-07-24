from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.split import SuggestionSource
from app.models.transaction import Transaction, TransactionType
from app.services.rule_engine import TransactionContext, find_matching_rule
from app.services.rules import list_rules, rules_to_specs


def list_eligible_for_suggestion(db: Session, transaction_ids: list[int] | None = None) -> list[Transaction]:
    """Transactions eligible for a rule/AI category suggestion: normal
    (non-transfer) transactions with a single split that has no confirmed
    category yet. A suggestion proposes one category for the transaction
    as a whole, and a transaction someone has already (fully or partially)
    split is left alone — only manual/AI-assisted editing touches those.
    """
    stmt = (
        select(Transaction)
        .options(selectinload(Transaction.splits))
        .where(Transaction.type == TransactionType.NORMAL)
    )
    if transaction_ids is not None:
        stmt = stmt.where(Transaction.id.in_(transaction_ids))

    transactions = db.execute(stmt).scalars().unique().all()
    return [t for t in transactions if len(t.splits) == 1 and t.splits[0].category_id is None]


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

    transactions = list_eligible_for_suggestion(db, transaction_ids)

    suggested_count = 0
    for txn in transactions:
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

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.errors import NotFoundError
from app.models.category import Category
from app.models.split import SuggestionSource
from app.models.transaction import Transaction
from app.services.categorization import list_eligible_for_suggestion


@dataclass
class AiSuggestionInput:
    transaction_id: int
    split_id: int
    category_id: int


@dataclass
class AiSuggestionResult:
    applied: int
    skipped: list[int]  # transaction_ids skipped because already confirmed


def list_uncategorized_for_ai(db: Session) -> list[Transaction]:
    """Transactions an external AI caller (e.g. the MCP skill) can propose
    a category for. AI categorization is on-demand only and never runs
    automatically (docs/requirements.md §3.2) — this endpoint just exposes
    what's eligible; the actual model call happens outside this app.
    """
    return list_eligible_for_suggestion(db)


def apply_ai_suggestions(db: Session, suggestions: list[AiSuggestionInput]) -> AiSuggestionResult:
    """Record AI-proposed categories using the same suggestion mechanism
    as rules (Split.suggested_category_id / suggestion_source), so they
    render through the same accept/reject UI. A split that's already
    confirmed (category_id set) is skipped rather than overwritten —
    AI suggestions never touch already-confirmed categories either.
    """
    applied = 0
    skipped: list[int] = []

    for s in suggestions:
        txn = db.get(Transaction, s.transaction_id)
        if txn is None:
            raise NotFoundError(f"Transaction {s.transaction_id} not found")
        split = next((sp for sp in txn.splits if sp.id == s.split_id), None)
        if split is None:
            raise NotFoundError(f"Split {s.split_id} not found on transaction {s.transaction_id}")
        if db.get(Category, s.category_id) is None:
            raise NotFoundError(f"Category {s.category_id} not found")

        if split.category_id is not None:
            skipped.append(s.transaction_id)
            continue

        split.suggested_category_id = s.category_id
        split.suggestion_source = SuggestionSource.AI
        applied += 1

    db.commit()
    return AiSuggestionResult(applied=applied, skipped=skipped)

from sqlalchemy.orm import Session


def run_categorization(db: Session, transaction_ids: list[int]) -> None:
    """Apply categorization rules to the given (currently uncategorized)
    transactions.

    Placeholder for milestone 5's rule engine: import must kick this off
    asynchronously right after import per docs/requirements.md §2.4, but
    no rules exist yet to apply. Wiring it in now (rather than after the
    rule engine lands) keeps the import code path stable.
    """
    return None

from decimal import ROUND_HALF_UP, Decimal

from app.errors import ValidationError

CENT = Decimal("0.01")


def _round(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def validate_splits(
    splits: list[tuple[int | None, float]], expected_total: float | None = None
) -> Decimal:
    """Validate a set of (category_id, amount) pairs for one transaction."""
    if not splits:
        raise ValidationError("A transaction must have at least one split")

    seen_categories: set[int | None] = set()
    total = Decimal("0")
    for category_id, amount in splits:
        if category_id in seen_categories:
            label = "uncategorized" if category_id is None else f"category {category_id}"
            raise ValidationError(f"Duplicate split for {label}: each category may appear at most once")
        seen_categories.add(category_id)
        total += _round(amount)

    if expected_total is not None and total != _round(expected_total):
        raise ValidationError(
            f"Splits must sum to the transaction total ({_round(expected_total)}), got {total}"
        )

    return total

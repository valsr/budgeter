import datetime as dt
import enum
import re
from dataclasses import dataclass
from decimal import Decimal


class MatchType(enum.Enum):
    EXACT = "exact"
    NEAR = "near"
    NONE = "none"


@dataclass
class ExistingTransaction:
    id: int
    date: dt.date
    amount: Decimal
    name: str


_PUNCTUATION_RE = re.compile(r"[^a-z0-9\s]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_name(text: str) -> str:
    """Lowercase, strip punctuation, and collapse whitespace."""
    lowered = text.lower()
    no_punct = _PUNCTUATION_RE.sub(" ", lowered)
    return _WHITESPACE_RE.sub(" ", no_punct).strip()


def classify_match(
    candidate_date: dt.date,
    candidate_amount: Decimal,
    candidate_name: str,
    existing: list[ExistingTransaction],
) -> tuple[MatchType, int | None]:
    """Classify a candidate import row against existing transactions on the same account."""
    candidate_key = normalize_name(candidate_name)
    same_date_amount = [
        e for e in existing if e.date == candidate_date and e.amount == candidate_amount
    ]
    if not same_date_amount:
        return MatchType.NONE, None

    for e in same_date_amount:
        if normalize_name(e.name) == candidate_key:
            return MatchType.EXACT, e.id

    return MatchType.NEAR, same_date_amount[0].id

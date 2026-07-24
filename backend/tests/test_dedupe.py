import datetime as dt
from decimal import Decimal

import pytest

from app.services.dedupe import ExistingTransaction, MatchType, classify_match, normalize_name


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("SPOTIFY *19.99", "spotify 19 99"),
        ("  Costco   Wholesale  ", "costco wholesale"),
        ("UBER TRIP HELP.UBER.COM", "uber trip help uber com"),
        ("Costco", "costco"),
    ],
)
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


def test_normalize_name_is_idempotent():
    assert normalize_name(normalize_name("SPOTIFY *19.99")) == normalize_name("SPOTIFY *19.99")


def _existing(id_, date, amount, name):
    return ExistingTransaction(id=id_, date=date, amount=Decimal(str(amount)), name=name)


def test_exact_match_same_normalized_name():
    existing = [_existing(1, dt.date(2026, 7, 19), -88.40, "Costco")]
    match, matched_id = classify_match(dt.date(2026, 7, 19), Decimal("-88.40"), "COSTCO", existing)
    assert match == MatchType.EXACT
    assert matched_id == 1


def test_exact_match_ignores_punctuation_differences():
    existing = [_existing(1, dt.date(2026, 7, 20), 19.99, "SPOTIFY *19.99")]
    match, matched_id = classify_match(
        dt.date(2026, 7, 20), Decimal("19.99"), "Spotify  19.99", existing
    )
    assert match == MatchType.EXACT
    assert matched_id == 1


def test_near_match_same_date_amount_different_name():
    existing = [_existing(1, dt.date(2026, 7, 19), -42.10, "Amazon Marketplace PENDING")]
    match, matched_id = classify_match(
        dt.date(2026, 7, 19), Decimal("-42.10"), "AMAZON.COM", existing
    )
    assert match == MatchType.NEAR
    assert matched_id == 1


def test_no_match_different_date():
    existing = [_existing(1, dt.date(2026, 7, 19), -88.40, "Costco")]
    match, matched_id = classify_match(dt.date(2026, 7, 20), Decimal("-88.40"), "Costco", existing)
    assert match == MatchType.NONE
    assert matched_id is None


def test_no_match_different_amount():
    existing = [_existing(1, dt.date(2026, 7, 19), -88.40, "Costco")]
    match, matched_id = classify_match(dt.date(2026, 7, 19), Decimal("-50.00"), "Costco", existing)
    assert match == MatchType.NONE
    assert matched_id is None


def test_no_existing_transactions():
    match, matched_id = classify_match(dt.date(2026, 7, 19), Decimal("-1.00"), "x", [])
    assert match == MatchType.NONE
    assert matched_id is None


def test_exact_match_preferred_over_near_when_both_present():
    existing = [
        _existing(1, dt.date(2026, 7, 19), -88.40, "Costco Pending"),
        _existing(2, dt.date(2026, 7, 19), -88.40, "Costco"),
    ]
    match, matched_id = classify_match(dt.date(2026, 7, 19), Decimal("-88.40"), "COSTCO", existing)
    assert match == MatchType.EXACT
    assert matched_id == 2

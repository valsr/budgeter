import datetime as dt
from decimal import Decimal

import pytest

from app.errors import ValidationError
from app.services.qif_parser import parse_qif


def test_parses_single_record():
    content = """!Type:Bank
D07/19/2026
T-88.40
PCostco
^
"""
    txns = parse_qif(content)
    assert len(txns) == 1
    t = txns[0]
    assert t.date == dt.date(2026, 7, 19)
    assert t.amount == Decimal("-88.40")
    assert t.payee == "Costco"
    assert t.name == "Costco"


def test_parses_multiple_records():
    content = """!Type:Bank
D07/19/2026
T-88.40
PCostco
^
D07/20/2026
T19.99
PSPOTIFY *19.99
^
"""
    txns = parse_qif(content)
    assert len(txns) == 2
    assert txns[1].payee == "SPOTIFY *19.99"
    assert txns[1].amount == Decimal("19.99")


def test_combines_payee_and_memo_for_name():
    content = """D07/19/2026
T-10.00
PCostco
MReceipt 123
^
"""
    txn = parse_qif(content)[0]
    assert txn.name == "Costco Receipt 123"


def test_memo_only_used_as_name_when_no_payee():
    content = """D07/19/2026
T-10.00
MJust a memo
^
"""
    txn = parse_qif(content)[0]
    assert txn.name == "Just a memo"


def test_missing_description_falls_back():
    content = """D07/19/2026
T-10.00
^
"""
    txn = parse_qif(content)[0]
    assert txn.name == "(no description)"


def test_u_field_used_as_amount_fallback():
    content = """D07/19/2026
U-10.00
PTest
^
"""
    txn = parse_qif(content)[0]
    assert txn.amount == Decimal("-10.00")


def test_ignores_unknown_fields():
    content = """D07/19/2026
T-10.00
PCostco
LGroceries
N1234
^
"""
    txn = parse_qif(content)[0]
    assert txn.payee == "Costco"


def test_ignores_header_and_blank_lines():
    content = """!Type:Bank

D07/19/2026
T-10.00
PCostco

^
"""
    txns = parse_qif(content)
    assert len(txns) == 1


def test_tolerates_missing_trailing_caret():
    content = """D07/19/2026
T-10.00
PCostco"""
    txns = parse_qif(content)
    assert len(txns) == 1


def test_amount_with_thousands_separator():
    content = """D07/19/2026
T-1,234.56
PBig purchase
^
"""
    txn = parse_qif(content)[0]
    assert txn.amount == Decimal("-1234.56")


def test_invalid_amount_raises():
    content = """D07/19/2026
Tnot-a-number
PCostco
^
"""
    with pytest.raises(ValidationError):
        parse_qif(content)


def test_invalid_date_raises():
    content = """Dnot-a-date
T-10.00
PCostco
^
"""
    with pytest.raises(ValidationError):
        parse_qif(content)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("07/19/2026", dt.date(2026, 7, 19)),
        ("7/19/2026", dt.date(2026, 7, 19)),
        ("07/19/26", dt.date(2026, 7, 19)),
        ("7/19'26", dt.date(2026, 7, 19)),
        ("2026-07-19", dt.date(2026, 7, 19)),
    ],
)
def test_date_formats(raw, expected):
    content = f"D{raw}\nT-1.00\nPx\n^\n"
    txn = parse_qif(content)[0]
    assert txn.date == expected


def test_empty_content_returns_no_transactions():
    assert parse_qif("") == []

    assert parse_qif("!Type:Bank\n") == []

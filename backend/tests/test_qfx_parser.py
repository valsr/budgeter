import datetime as dt
from decimal import Decimal

import pytest

from app.errors import ValidationError
from app.services.qfx_parser import looks_like_qfx, parse_qfx, parse_qfx_accounts

BANK_STMT = """OFXHEADER:100
DATA:OFXSGML
VERSION:102

<OFX>
<BANKMSGSRSV1>
<STMTTRNRS>
<STMTRS>
<CURDEF>USD
<BANKACCTFROM>
<BANKID>123456789
<ACCTID>1234567890
<ACCTTYPE>CHECKING
</BANKACCTFROM>
<BANKTRANLIST>
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20260719120000[-5:EST]
<TRNAMT>-88.40
<FITID>202607190001
<NAME>COSTCO
<MEMO>Whse #123
</STMTTRN>
<STMTTRN>
<TRNTYPE>CREDIT
<DTPOSTED>20260720
<TRNAMT>1234.56
<FITID>202607200001
<NAME>PAYROLL
</STMTTRN>
</BANKTRANLIST>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>
"""

CCARD_STMT = """<OFX>
<CREDITCARDMSGSRSV1>
<CCSTMTTRNRS>
<CCSTMTRS>
<CCACCTFROM>
<ACCTID>4111000011112222
</CCACCTFROM>
<BANKTRANLIST>
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20260721
<TRNAMT>-55.00
<NAME>AMAZON
</STMTTRN>
</BANKTRANLIST>
</CCSTMTRS>
</CCSTMTTRNRS>
</CREDITCARDMSGSRSV1>
</OFX>
"""


def test_parses_bank_statement_with_account():
    blocks = parse_qfx_accounts(BANK_STMT)
    assert len(blocks) == 1
    block = blocks[0]
    assert block.name == "1234567890"
    assert block.account_type_hint == "asset"
    assert len(block.transactions) == 2

    t0 = block.transactions[0]
    assert t0.date == dt.date(2026, 7, 19)
    assert t0.amount == Decimal("-88.40")
    assert t0.payee == "COSTCO"
    assert t0.memo == "Whse #123"

    t1 = block.transactions[1]
    assert t1.date == dt.date(2026, 7, 20)
    assert t1.amount == Decimal("1234.56")
    assert t1.payee == "PAYROLL"
    assert t1.memo == ""


def test_ccacctfrom_maps_to_liability():
    blocks = parse_qfx_accounts(CCARD_STMT)
    assert len(blocks) == 1
    assert blocks[0].name == "4111000011112222"
    assert blocks[0].account_type_hint == "liability"
    assert blocks[0].transactions[0].payee == "AMAZON"


def test_multiple_stmttrnrs_sections_produce_multiple_blocks():
    # A multi-account OFX aggregation response sends one STMTTRNRS per
    # account within a single BANKMSGSRSV1.
    content = """<OFX>
<BANKMSGSRSV1>
<STMTTRNRS>
<STMTRS>
<BANKACCTFROM>
<ACCTID>Checking-1
</BANKACCTFROM>
<BANKTRANLIST>
<STMTTRN>
<DTPOSTED>20260719
<TRNAMT>-1.00
<NAME>A</NAME>
</STMTTRN>
</BANKTRANLIST>
</STMTRS>
</STMTTRNRS>
<STMTTRNRS>
<STMTRS>
<BANKACCTFROM>
<ACCTID>Savings-1
</BANKACCTFROM>
<BANKTRANLIST>
<STMTTRN>
<DTPOSTED>20260720
<TRNAMT>500.00
<NAME>B</NAME>
</STMTTRN>
</BANKTRANLIST>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>
"""
    blocks = parse_qfx_accounts(content)
    assert [(b.name, [t.payee for t in b.transactions]) for b in blocks] == [
        ("Checking-1", ["A"]),
        ("Savings-1", ["B"]),
    ]


def test_parse_qfx_flattens_to_transaction_list():
    txns = parse_qfx(BANK_STMT)
    assert len(txns) == 2
    assert [t.payee for t in txns] == ["COSTCO", "PAYROLL"]


def test_ignores_unrecognized_tags():
    content = """<OFX>
<BANKMSGSRSV1>
<STMTTRNRS>
<STMTRS>
<BANKACCTFROM>
<ACCTID>555
</BANKACCTFROM>
<BANKTRANLIST>
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20260719
<TRNAMT>-1.00
<CHECKNUM>1042
<NAME>Test
</STMTTRN>
</BANKTRANLIST>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>
"""
    txns = parse_qfx(content)
    assert len(txns) == 1
    assert txns[0].payee == "Test"


def test_handles_ofx2_xml_style_same_line_closing_tags():
    content = """<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS>
<BANKACCTFROM><ACCTID>1234567890</ACCTID><ACCTTYPE>CHECKING</ACCTTYPE></BANKACCTFROM>
<BANKTRANLIST>
<STMTTRN>
<DTPOSTED>20260719</DTPOSTED>
<TRNAMT>-88.40</TRNAMT>
<NAME>COSTCO</NAME>
<MEMO>Whse #123</MEMO>
</STMTTRN>
</BANKTRANLIST>
</STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>
"""
    blocks = parse_qfx_accounts(content)
    assert len(blocks) == 1
    assert blocks[0].name == "1234567890"
    assert blocks[0].account_type_hint == "asset"
    t = blocks[0].transactions[0]
    assert t.date == dt.date(2026, 7, 19)
    assert t.amount == Decimal("-88.40")
    assert t.payee == "COSTCO"
    assert t.memo == "Whse #123"


def test_invalid_date_raises():
    content = """<STMTTRN>
<DTPOSTED>not-a-date
<TRNAMT>-1.00
</STMTTRN>
"""
    with pytest.raises(ValidationError):
        parse_qfx(content)


def test_empty_content_returns_no_transactions():
    assert parse_qfx("") == []


@pytest.mark.parametrize(
    "filename,content,expected",
    [
        ("statement.qfx", "", True),
        ("statement.ofx", "", True),
        ("statement.qif", "OFXHEADER:100", False),
        ("statement.txt", "OFXHEADER:100\nDATA:OFXSGML\n", True),
        ("statement.txt", "<OFX><BANKMSGSRSV1>", True),
        ("statement.txt", "!Type:Bank\nD07/19/2026\n", False),
    ],
)
def test_looks_like_qfx(filename, content, expected):
    assert looks_like_qfx(filename, content) is expected

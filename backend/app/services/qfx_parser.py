import datetime as dt
import re

from app.errors import ValidationError
from app.services.qif_parser import QifAccountBlock, QifTransaction, parse_amount

# QFX (Quicken Financial Exchange) is Intuit's variant of OFX. Most bank
# exports still use OFX 1.x SGML, one tag per line with no closing pairs
# (`<TRNAMT>-88.40`); some use OFX 2.x XML, which does close tags — often
# several per line (`<ACCTID>123</ACCTID><ACCTTYPE>CHECKING</ACCTTYPE>`).
# Scanning for every `<TAG>value` token on a line (rather than assuming one
# tag per line) handles both without a real SGML/XML parser.
_TAG_TOKEN = re.compile(r"<(/?)([A-Za-z0-9.]+)>([^<]*)")

_STMTTRNRS = "STMTTRNRS"
_ACCOUNT_CONTAINERS = ("BANKACCTFROM", "CCACCTFROM")
_STMTTRN = "STMTTRN"


def _tokenize(content: str):
    for raw_line in content.splitlines():
        for m in _TAG_TOKEN.finditer(raw_line):
            closing, tag, value = m.group(1) == "/", m.group(2).upper(), m.group(3).strip()
            yield tag, closing, value


def _parse_ofx_date(raw: str) -> dt.date:
    # DTPOSTED is YYYYMMDD, optionally followed by time/timezone
    # (e.g. "20260719120000[-5:EST]") which we don't need.
    digits = raw.strip()[:8]
    try:
        return dt.datetime.strptime(digits, "%Y%m%d").date()
    except ValueError as e:
        raise ValidationError(f"Invalid QFX date: {raw!r}") from e


def parse_qfx_accounts(content: str) -> list[QifAccountBlock]:
    """Parse an OFX/QFX file's contents into one block of transactions per
    account. Unlike QIF, every OFX statement declares its account explicitly
    (`<BANKACCTFROM>`/`<CCACCTFROM>` with an `<ACCTID>`), so every block here
    has a `name` — there's no single-account "implicit" case as in QIF.
    """
    blocks: list[QifAccountBlock] = []
    account_name: str | None = None
    account_type_hint: str | None = None
    txns: list[QifTransaction] = []

    in_account_container = False
    in_txn = False
    date: dt.date | None = None
    amount = None
    payee = ""
    memo = ""

    def flush_txn() -> None:
        nonlocal date, amount, payee, memo, in_txn
        if date is not None and amount is not None:
            txns.append(QifTransaction(date=date, amount=amount, payee=payee, memo=memo))
        date, amount, payee, memo, in_txn = None, None, "", "", False

    def flush_block() -> None:
        nonlocal txns
        if txns:
            blocks.append(
                QifAccountBlock(name=account_name, account_type_hint=account_type_hint, transactions=txns)
            )
        txns = []

    for tag, closing, value in _tokenize(content):
        if tag == _STMTTRNRS and not closing:
            flush_txn()
            flush_block()
            account_name, account_type_hint = None, None
            continue

        if tag in _ACCOUNT_CONTAINERS:
            in_account_container = not closing
            if not closing:
                account_type_hint = "liability" if tag == "CCACCTFROM" else "asset"
            continue

        if in_account_container and tag == "ACCTID" and not closing:
            account_name = value.strip()
            continue

        if tag == _STMTTRN:
            flush_txn()
            in_txn = not closing
            continue

        if not in_txn or closing:
            # A leaf field's own closing token (e.g. the `</NAME>` half of
            # "<NAME>A</NAME>") carries no value — skip it, or it would
            # overwrite what the opening token just set.
            continue

        if tag == "DTPOSTED":
            date = _parse_ofx_date(value)
        elif tag == "TRNAMT":
            amount = parse_amount(value)
        elif tag in ("NAME", "PAYEE"):
            payee = value.strip()
        elif tag == "MEMO":
            memo = value.strip()
        # else: unrecognized field (FITID, TRNTYPE, CHECKNUM, ...), ignored

    flush_txn()
    flush_block()
    return blocks


def parse_qfx(content: str) -> list[QifTransaction]:
    """Parse an OFX/QFX file's contents into a flat list of transactions,
    ignoring account boundaries (see parse_qfx_accounts)."""
    return [txn for block in parse_qfx_accounts(content) for txn in block.transactions]


def looks_like_qfx(filename: str, content: str) -> bool:
    """Format sniffing for the import endpoints: extension first, falling
    back to content (some banks mislabel the extension)."""
    lower = filename.lower()
    if lower.endswith((".qfx", ".ofx")):
        return True
    if lower.endswith(".qif"):
        return False
    head = content[:1000].upper()
    return "OFXHEADER" in head or "<OFX>" in head

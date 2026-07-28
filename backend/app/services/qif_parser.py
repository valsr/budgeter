import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from app.errors import ValidationError

# QIF field codes we care about; anything else (N check#, A address, S/E/$
# QIF-native splits, etc.) is ignored for robustness rather than erroring.
_DATE = "D"
_AMOUNT_CODES = ("T", "U")
_PAYEE = "P"
_MEMO = "M"
_RECORD_END = "^"
_HEADER_PREFIX = "!"
_ACCOUNT_SECTION = "!Account"

# Fields within an !Account list header (distinct namespace from transaction
# fields, since we're in a different parse mode while reading it).
_ACCT_NAME = "N"
_ACCT_TYPE = "T"

# QIF account-type strings map onto our two-way asset/liability model.
_LIABILITY_TYPES = {"ccard", "oth l", "othl"}


def _map_account_type(raw: str) -> str:
    return "liability" if raw.strip().lower() in _LIABILITY_TYPES else "asset"


@dataclass
class QifTransaction:
    date: dt.date
    amount: Decimal
    payee: str
    memo: str

    @property
    def name(self) -> str:
        if self.payee and self.memo:
            return f"{self.payee} {self.memo}"
        return self.payee or self.memo or "(no description)"


@dataclass
class QifAccountBlock:
    """Transactions belonging to one account within a QIF file.

    `name` is None for single-account exports, which have no `!Account`
    header at all — the caller supplies the target account out of band.
    Multi-account (Quicken-style) exports declare each account via an
    `!Account` header block (N=name, T=type) immediately before the
    `!Type:...` section of transactions that belong to it.
    """

    name: str | None
    account_type_hint: str | None
    transactions: list[QifTransaction] = field(default_factory=list)


def parse_amount(raw: str) -> Decimal:
    cleaned = raw.strip().replace(",", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation as e:
        raise ValidationError(f"Invalid QIF amount: {raw!r}") from e


def _parse_date(raw: str) -> dt.date:
    raw = raw.strip()
    if "'" in raw:
        left, year_part = raw.split("'", 1)
        year_part = year_part.strip()
        year = 2000 + int(year_part) if len(year_part) <= 2 else int(year_part)
        raw = f"{left}/{year}"

    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return dt.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValidationError(f"Invalid QIF date: {raw!r}")


def parse_qif_accounts(content: str) -> list[QifAccountBlock]:
    """Parse a QIF file's contents into one block of transactions per
    account. Only the Bank/CCard-style single-line transaction fields we
    need (date, amount, payee, memo) are extracted; QIF's own split syntax
    and other record types are not supported (splits are managed within
    this app, not imported pre-split).

    Single-account exports (the common case) have no `!Account` header at
    all, so this returns a single block with `name=None` — the caller is
    expected to already know which account the file belongs to. Multi-
    account (Quicken-style) exports interleave `!Account` header blocks
    (N=name, T=type) with the `!Type:...` transaction sections that follow
    each one; those produce one named block per account.
    """
    blocks: list[QifAccountBlock] = []
    account_name: str | None = None
    account_type_hint: str | None = None
    txns: list[QifTransaction] = []
    in_account_header = False
    pending_name: str | None = None
    pending_type_hint: str | None = None

    date: dt.date | None = None
    amount: Decimal | None = None
    payee = ""
    memo = ""

    def flush_transaction() -> None:
        nonlocal date, amount, payee, memo
        if date is not None and amount is not None:
            txns.append(QifTransaction(date=date, amount=amount, payee=payee, memo=memo))
        date, amount, payee, memo = None, None, "", ""

    def flush_block() -> None:
        nonlocal txns
        if txns:
            blocks.append(
                QifAccountBlock(name=account_name, account_type_hint=account_type_hint, transactions=txns)
            )
        txns = []

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith(_ACCOUNT_SECTION):
            flush_transaction()
            flush_block()
            in_account_header = True
            pending_name, pending_type_hint = None, None
            continue

        if line.startswith(_HEADER_PREFIX):
            flush_transaction()
            if in_account_header:
                account_name, account_type_hint = pending_name, pending_type_hint
                in_account_header = False
            continue

        code, value = line[0], line[1:]

        if in_account_header:
            if code == _ACCT_NAME:
                pending_name = value.strip()
            elif code == _ACCT_TYPE:
                pending_type_hint = _map_account_type(value)
            # else: unrecognized account-header field (record separator
            # included), ignored — nothing else to capture here.
            continue

        if code == _RECORD_END:
            flush_transaction()
        elif code == _DATE:
            date = _parse_date(value)
        elif code in _AMOUNT_CODES:
            amount = parse_amount(value)
        elif code == _PAYEE:
            payee = value.strip()
        elif code == _MEMO:
            memo = value.strip()
        # else: unrecognized field code, ignored

    flush_transaction()  # tolerate a missing trailing '^'
    flush_block()
    return blocks


def parse_qif(content: str) -> list[QifTransaction]:
    """Parse a QIF file's contents into a flat list of transactions,
    ignoring any account boundaries (see parse_qif_accounts)."""
    return [txn for block in parse_qif_accounts(content) for txn in block.transactions]

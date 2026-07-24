import datetime as dt
from dataclasses import dataclass
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


def _parse_amount(raw: str) -> Decimal:
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


def parse_qif(content: str) -> list[QifTransaction]:
    """Parse a QIF file's contents into a flat list of transactions.

    Only the Bank/CCard-style single-line transaction fields we need
    (date, amount, payee, memo) are extracted; QIF's own split syntax and
    other record types are not supported (splits are managed within this
    app, not imported pre-split).
    """
    transactions: list[QifTransaction] = []
    date: dt.date | None = None
    amount: Decimal | None = None
    payee = ""
    memo = ""

    def flush() -> None:
        nonlocal date, amount, payee, memo
        if date is not None and amount is not None:
            transactions.append(QifTransaction(date=date, amount=amount, payee=payee, memo=memo))
        date, amount, payee, memo = None, None, "", ""

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(_HEADER_PREFIX):
            continue
        code, value = line[0], line[1:]
        if code == _RECORD_END:
            flush()
        elif code == _DATE:
            date = _parse_date(value)
        elif code in _AMOUNT_CODES:
            amount = _parse_amount(value)
        elif code == _PAYEE:
            payee = value.strip()
        elif code == _MEMO:
            memo = value.strip()
        # else: unrecognized field code, ignored

    flush()  # tolerate a missing trailing '^'
    return transactions

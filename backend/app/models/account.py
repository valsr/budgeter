import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AccountType(str, enum.Enum):
    ASSET = "asset"
    LIABILITY = "liability"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    account_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    type: Mapped[AccountType] = mapped_column(Enum(AccountType), nullable=False)
    opening_balance: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

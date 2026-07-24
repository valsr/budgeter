import enum
from datetime import date as date_, datetime, timezone

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TransactionType(str, enum.Enum):
    NORMAL = "normal"
    TRANSFER = "transfer"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    date: Mapped[date_] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType), nullable=False, default=TransactionType.NORMAL
    )
    transfer_pair_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    splits: Mapped[list["Split"]] = relationship(  # noqa: F821
        "Split", back_populates="transaction", cascade="all, delete-orphan"
    )

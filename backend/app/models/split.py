import enum

from sqlalchemy import Enum, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class SuggestionSource(str, enum.Enum):
    RULE = "rule"
    AI = "ai"


class Split(Base):
    __tablename__ = "splits"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id"), nullable=False
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    suggested_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    suggestion_source: Mapped[SuggestionSource | None] = mapped_column(
        Enum(SuggestionSource), nullable=True
    )

    transaction: Mapped["Transaction"] = relationship(  # noqa: F821
        "Transaction", back_populates="splits"
    )

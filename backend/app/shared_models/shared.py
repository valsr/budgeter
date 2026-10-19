from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared_db import SharedBase


class SharedCategory(SharedBase):
    __tablename__ = "shared_categories"
    # AUTOINCREMENT: a deleted category's id must never come back, or members' links
    # (kept in their own books, out of reach of this file's cascades) would revive.
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("shared_categories.id"), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_income: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    children: Mapped[list["SharedCategory"]] = relationship(
        "SharedCategory",
        back_populates="parent",
        order_by="SharedCategory.sort_order",
    )
    parent: Mapped["SharedCategory | None"] = relationship(
        "SharedCategory", back_populates="children", remote_side=[id]
    )


class SharedBudgetAmount(SharedBase):
    """The budgeted amount for one shared category in one month."""

    __tablename__ = "shared_budget_amounts"
    __table_args__ = (UniqueConstraint("shared_category_id", "year", "month", name="uq_shared_amount_period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shared_category_id: Mapped[int] = mapped_column(
        ForeignKey("shared_categories.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)


class MemberTally(SharedBase):
    """What one member has spent against a shared category in one month."""

    __tablename__ = "member_tallies"
    __table_args__ = (
        UniqueConstraint("user_id", "shared_category_id", "year", "month", name="uq_member_tally_period"),
        Index("ix_member_tallies_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    shared_category_id: Mapped[int] = mapped_column(
        ForeignKey("shared_categories.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

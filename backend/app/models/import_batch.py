import enum
from datetime import date as date_
from datetime import datetime, timezone

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ReviewItemStatus(str, enum.Enum):
    PENDING = "pending"
    RESOLVED_NEW = "resolved_new"
    RESOLVED_MERGED = "resolved_merged"
    RESOLVED_SKIPPED = "resolved_skipped"


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    needs_review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    review_items: Mapped[list["ReviewQueueItem"]] = relationship(
        "ReviewQueueItem", back_populates="import_batch", cascade="all, delete-orphan"
    )


class ReviewQueueItem(Base):
    __tablename__ = "review_queue_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    import_batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.id"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    date: Mapped[date_] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    candidate_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id"), nullable=True
    )
    status: Mapped[ReviewItemStatus] = mapped_column(
        Enum(ReviewItemStatus), nullable=False, default=ReviewItemStatus.PENDING
    )

    import_batch: Mapped["ImportBatch"] = relationship(
        "ImportBatch", back_populates="review_items"
    )

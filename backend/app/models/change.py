import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ChangeOperation(str, enum.Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class _ChangeRow:
    """Shared column set for the three per-entity change-log tables."""

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    group_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    operation: Mapped[ChangeOperation] = mapped_column(Enum(ChangeOperation), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AccountChange(_ChangeRow, Base):
    __tablename__ = "account_changes"


class CategoryChange(_ChangeRow, Base):
    __tablename__ = "category_changes"


class TransactionChange(_ChangeRow, Base):
    __tablename__ = "transaction_changes"


class AppSettings(Base):
    """Single-row table holding one user's settings for their own books."""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

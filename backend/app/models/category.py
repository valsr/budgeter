from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    children: Mapped[list["Category"]] = relationship(
        "Category",
        back_populates="parent",
        order_by="Category.sort_order",
    )
    parent: Mapped["Category | None"] = relationship(
        "Category", back_populates="children", remote_side=[id]
    )

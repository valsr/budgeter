from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SharedCategoryLink(Base):
    """Maps one of this user's categories to a category in a shared budget.

    The shared ids point into shared/<id>.db, a different file, so they are plain integers
    rather than foreign keys."""

    __tablename__ = "shared_category_links"
    __table_args__ = (
        UniqueConstraint("shared_budget_id", "category_id", name="uq_shared_link_category"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    shared_budget_id: Mapped[int] = mapped_column(nullable=False)
    shared_category_id: Mapped[int] = mapped_column(nullable=False)

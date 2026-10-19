from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.server_db import ServerBase
from app.server_models.user import utcnow


class SharedBudget(ServerBase):
    """Registry entry for a shared budget; its data lives in shared/<id>.db."""

    __tablename__ = "shared_budgets"
    # AUTOINCREMENT: an id is never handed out twice, so a deleted budget's file is never reused.
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    members: Mapped[list["SharedBudgetMember"]] = relationship(
        "SharedBudgetMember", back_populates="shared_budget", cascade="all, delete-orphan"
    )


class SharedBudgetMember(ServerBase):
    __tablename__ = "shared_budget_members"

    shared_budget_id: Mapped[int] = mapped_column(ForeignKey("shared_budgets.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)

    shared_budget: Mapped["SharedBudget"] = relationship("SharedBudget", back_populates="members")

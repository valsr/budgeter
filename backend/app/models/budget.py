from sqlalchemy import ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Budget(Base):
    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    budget_categories: Mapped[list["BudgetCategory"]] = relationship(
        "BudgetCategory", back_populates="budget", cascade="all, delete-orphan"
    )


class BudgetCategory(Base):
    __tablename__ = "budget_categories"
    __table_args__ = (UniqueConstraint("budget_id", "category_id", name="uq_budget_category"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    budget_id: Mapped[int] = mapped_column(ForeignKey("budgets.id"), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)

    budget: Mapped["Budget"] = relationship("Budget", back_populates="budget_categories")
    amounts: Mapped[list["BudgetAmount"]] = relationship(
        "BudgetAmount", back_populates="budget_category", cascade="all, delete-orphan"
    )


class BudgetAmount(Base):
    __tablename__ = "budget_amounts"
    __table_args__ = (
        UniqueConstraint("budget_category_id", "year", "month", name="uq_budget_amount_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    budget_category_id: Mapped[int] = mapped_column(
        ForeignKey("budget_categories.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    budget_category: Mapped["BudgetCategory"] = relationship(
        "BudgetCategory", back_populates="amounts"
    )

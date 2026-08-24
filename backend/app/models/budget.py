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
    """One budgeted line: a category, optionally narrowed to a single account.

    `account_id` NULL budgets the category as a whole. Set, it budgets that
    category's spending from that one account -- so a category can be planned
    per source ("groceries on Main, groceries on Visa") when a downstream
    system needs the split.

    A category uses one mode or the other, never both at once: a NULL line
    alongside account lines would leave "the groceries budget" ambiguous
    between the NULL row and the sum of the account rows. The unique
    constraint can't express that (SQL treats NULLs as distinct, so it won't
    even stop two NULL lines), so budgets._partition_categories enforces it.
    """

    __tablename__ = "budget_categories"
    __table_args__ = (
        UniqueConstraint("budget_id", "category_id", "account_id", name="uq_budget_category"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    budget_id: Mapped[int] = mapped_column(ForeignKey("budgets.id"), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)

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

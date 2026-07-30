import enum

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class MatchType(str, enum.Enum):
    ANY = "any"
    ALL = "all"


class ConditionField(str, enum.Enum):
    DATE = "date"
    DAY_OF_MONTH = "day_of_month"
    NAME = "name"
    ACCOUNT = "account"
    AMOUNT = "amount"


class ConditionOperator(str, enum.Enum):
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    EQUALS = "equals"
    LESS_THAN = "less_than"
    GREATER_THAN = "greater_than"
    IS_DEPOSIT = "is_deposit"
    """Amount field only: matches any deposit/credit (a positive split),
    ignoring the condition's value entirely -- see evaluate_condition."""
    IS_WITHDRAWAL = "is_withdrawal"
    """Amount field only: matches any withdrawal/debit (a negative split),
    ignoring the condition's value entirely -- see evaluate_condition."""


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_type: Mapped[MatchType] = mapped_column(Enum(MatchType), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id"), nullable=False
    )

    conditions: Mapped[list["RuleCondition"]] = relationship(
        "RuleCondition", back_populates="rule", cascade="all, delete-orphan"
    )


class RuleCondition(Base):
    __tablename__ = "rule_conditions"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("rules.id"), nullable=False)
    field: Mapped[ConditionField] = mapped_column(Enum(ConditionField), nullable=False)
    operator: Mapped[ConditionOperator] = mapped_column(Enum(ConditionOperator), nullable=False)
    value: Mapped[str] = mapped_column(String(300), nullable=False)

    rule: Mapped["Rule"] = relationship("Rule", back_populates="conditions")

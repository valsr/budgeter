from typing import Literal

from pydantic import BaseModel, ConfigDict


class BudgetCategoryInput(BaseModel):
    category_id: int
    monthly_amounts: dict[int, float]  # month (1-12) -> budgeted amount
    account_id: int | None = None
    """Narrows this line to one source account. Omit to budget the category as
    a whole. A category uses one mode or the other, never both."""


class BudgetCreate(BaseModel):
    name: str
    year: int
    categories: list[BudgetCategoryInput]


class BudgetUpdate(BaseModel):
    name: str | None = None
    year: int | None = None
    categories: list[BudgetCategoryInput] | None = None


class BudgetAmountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    month: int
    amount: float


class BudgetCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category_id: int
    account_id: int | None
    amounts: list[BudgetAmountRead]


class DroppedCategoryRead(BaseModel):
    """A category the save request listed that is no longer budgetable and was
    left out. `name` is null when the category has been deleted outright."""

    category_id: int
    name: str | None
    reason: Literal["removed", "archived", "broken_down", "account_removed"]
    account_id: int | None = None


class BudgetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    budget_categories: list[BudgetCategoryRead]
    # Only ever non-empty on a create/update response; reads never drop
    # anything, so it defaults empty rather than being optional.
    dropped_categories: list[DroppedCategoryRead] = []


class MonthCell(BaseModel):
    budgeted: float
    actual: float


class ReportRowRead(BaseModel):
    row_key: str
    """Unique per row. category_id stopped being unique once a category can be
    followed by per-account breakdown rows."""

    category_id: int
    account_id: int | None = None
    name: str
    is_parent: bool
    monthly: dict[int, MonthCell]
    ytd_diff: float
    has_budget: bool = True
    depth: int = 0
    is_income: bool = False

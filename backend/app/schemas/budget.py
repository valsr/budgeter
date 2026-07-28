from pydantic import BaseModel, ConfigDict


class BudgetCategoryInput(BaseModel):
    category_id: int
    monthly_amounts: dict[int, float]  # month (1-12) -> budgeted amount


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
    amounts: list[BudgetAmountRead]


class BudgetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    budget_categories: list[BudgetCategoryRead]


class MonthCell(BaseModel):
    budgeted: float
    actual: float


class ReportRowRead(BaseModel):
    category_id: int
    name: str
    is_parent: bool
    monthly: dict[int, MonthCell]
    ytd_diff: float
    has_budget: bool = True
    depth: int = 0

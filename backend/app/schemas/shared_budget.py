from pydantic import BaseModel, ConfigDict, Field

from app.schemas.budget import MonthCell


class SharedMemberRead(BaseModel):
    user_id: int
    username: str
    is_disabled: bool


class SharedBudgetRead(BaseModel):
    id: int
    name: str
    members: list[SharedMemberRead]


class SharedBudgetCreate(BaseModel):
    name: str
    member_ids: list[int] = []


class SharedBudgetUpdate(BaseModel):
    name: str


class SharedMembersUpdate(BaseModel):
    user_ids: list[int]


class DirectoryUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


class SharedCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    parent_id: int | None
    sort_order: int
    is_income: bool
    archived: bool


class SharedCategoryCreate(BaseModel):
    name: str
    parent_id: int | None = None
    is_income: bool = False


class SharedCategoryUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    sort_order: int | None = None
    is_income: bool | None = None
    archived: bool | None = None


class SharedAmountRead(BaseModel):
    shared_category_id: int
    month: int
    amount: float


class SharedAmountLine(BaseModel):
    shared_category_id: int
    month: int
    amount: float | None = None


class SharedAmountsUpdate(BaseModel):
    year: int
    lines: list[SharedAmountLine]


class SharedLinkRead(BaseModel):
    category_id: int
    shared_category_id: int


class SharedLinksUpdate(BaseModel):
    links: list[SharedLinkRead] = Field(default_factory=list)


class MemberSliceRead(BaseModel):
    user_id: int
    username: str
    monthly: dict[int, float]
    ytd_actual: float


class SharedReportRowRead(BaseModel):
    row_key: str
    category_id: int
    account_id: int | None = None
    name: str
    is_parent: bool
    monthly: dict[int, MonthCell]
    ytd_diff: float
    has_budget: bool = True
    depth: int = 0
    is_income: bool = False
    members: list[MemberSliceRead]

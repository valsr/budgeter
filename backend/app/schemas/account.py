from pydantic import BaseModel, ConfigDict

from app.models.account import AccountType


class AccountBase(BaseModel):
    name: str
    account_number: str | None = None
    type: AccountType
    opening_balance: float = 0
    color: str | None = None


class AccountCreate(AccountBase):
    pass


class AccountUpdate(BaseModel):
    name: str | None = None
    account_number: str | None = None
    type: AccountType | None = None
    opening_balance: float | None = None
    color: str | None = None


class AccountRead(AccountBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    balance: float

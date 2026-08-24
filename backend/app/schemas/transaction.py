import datetime as dt

from pydantic import BaseModel, ConfigDict

from app.models.split import SuggestionSource
from app.models.transaction import TransactionType


class SplitInputSchema(BaseModel):
    category_id: int | None = None
    amount: float


class SplitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int | None
    amount: float
    suggested_category_id: int | None = None
    suggestion_source: SuggestionSource | None = None


class TransactionCreate(BaseModel):
    account_id: int
    date: dt.date
    name: str
    splits: list[SplitInputSchema]


class TransactionUpdate(BaseModel):
    date: dt.date | None = None
    name: str | None = None


class SplitsUpdate(BaseModel):
    splits: list[SplitInputSchema]


class TransferCreate(BaseModel):
    from_account_id: int
    to_account_id: int
    date: dt.date
    name: str
    amount: float


class TransferLink(BaseModel):
    other_transaction_id: int


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    date: dt.date
    name: str
    type: TransactionType
    transfer_pair_id: int | None
    splits: list[SplitRead]


class TransactionPage(BaseModel):
    items: list[TransactionRead]
    total: int
    page: int
    page_size: int

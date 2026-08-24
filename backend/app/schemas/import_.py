import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.import_batch import ReviewItemStatus


class ImportBatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    account_id: int
    imported_at: dt.datetime
    row_count: int
    imported_count: int
    skipped_duplicate_count: int
    needs_review_count: int


class ReviewQueueItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    import_batch_id: int
    account_id: int
    date: dt.date
    amount: float
    name: str
    candidate_transaction_id: int | None
    status: ReviewItemStatus


class ReviewResolveRequest(BaseModel):
    action: Literal["new", "merge", "skip"]


class DetectedAccount(BaseModel):
    parsed_name: str | None
    transaction_count: int
    matched_account_id: int | None
    match_reason: Literal["name", "account_number"] | None = None
    suggested_type: Literal["asset", "liability"] | None = None
    # Which account the counts below were computed against — the auto-match
    # unless the caller overrode it. None means "a new account", so every row
    # counts as new.
    target_account_id: int | None = None
    new_count: int = 0
    duplicate_count: int = 0
    needs_review_count: int = 0


class DetectAccountsResponse(BaseModel):
    has_account_sections: bool
    accounts: list[DetectedAccount]


class DetectAccountsOverride(BaseModel):
    parsed_name: str | None
    # None = "the user chose to create a new account for this block".
    account_id: int | None = None


class DetectAccountsRequest(BaseModel):
    overrides: list[DetectAccountsOverride] = []


class NewAccountInput(BaseModel):
    name: str
    type: Literal["asset", "liability"]
    account_number: str | None = None
    opening_balance: float = 0
    color: str | None = None


class ImportResolution(BaseModel):
    parsed_name: str | None
    account_id: int | None = None
    new_account: NewAccountInput | None = None


class ImportCommitRequest(BaseModel):
    resolutions: list[ImportResolution]

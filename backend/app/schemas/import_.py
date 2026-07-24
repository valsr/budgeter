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

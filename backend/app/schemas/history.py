from datetime import datetime

from pydantic import BaseModel

from app.models.change import ChangeOperation


class ChangeItem(BaseModel):
    entity_id: int
    before: dict | None
    after: dict | None


class ChangeGroup(BaseModel):
    group_id: str
    entity_type: str
    operation: ChangeOperation
    summary: str
    created_at: datetime
    undone_at: datetime | None
    is_stale: bool
    items: list[ChangeItem]


class HistoryPage(BaseModel):
    items: list[ChangeGroup]
    total: int
    page: int
    page_size: int


class UndoRequest(BaseModel):
    group_ids: list[str]


class UndoResult(BaseModel):
    group_id: str
    status: str
    reason: str | None = None


class UndoResponse(BaseModel):
    results: list[UndoResult]

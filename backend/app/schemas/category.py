from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CategoryCreate(BaseModel):
    name: str
    parent_id: int | None = None
    color: str | None = None


class CategoryUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
    parent_id: int | None = None
    move_to_root: bool = False
    """Set true to explicitly move a category to top-level (parent_id=None)."""


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    parent_id: int | None
    color: str
    """Effective color: the stored override, or the deterministic hash-based default."""
    sort_order: int
    archived_at: datetime | None
    children: list["CategoryRead"] = []


class CategoryReorderRequest(BaseModel):
    parent_id: int | None = None
    ordered_ids: list[int]

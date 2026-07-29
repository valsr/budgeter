from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.db import get_db
from app.errors import ValidationError
from app.schemas.history import (
    ChangeGroup,
    ChangeItem,
    HistoryPage,
    UndoRequest,
    UndoResponse,
    UndoResult,
)
from app.services import history as history_service
from app.services import undo as undo_service

router = APIRouter(prefix="/api/history", tags=["history"], dependencies=[Depends(require_api_key)])


@router.get("", response_model=HistoryPage)
def list_history(
    entity_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    try:
        groups, total = history_service.list_changes(
            db,
            entity_type=entity_type,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        )
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    return HistoryPage(
        items=[
            ChangeGroup(
                group_id=g.group_id,
                entity_type=g.entity_type,
                operation=g.operation,
                summary=g.summary,
                created_at=g.created_at,
                undone_at=g.undone_at,
                is_stale=g.is_stale,
                items=[
                    ChangeItem(entity_id=i.entity_id, before=i.before, after=i.after) for i in g.items
                ],
            )
            for g in groups
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/undo", response_model=UndoResponse)
def undo_changes(payload: UndoRequest, db: Session = Depends(get_db)):
    outcomes = undo_service.undo_groups(db, payload.group_ids)
    return UndoResponse(
        results=[UndoResult(group_id=o.group_id, status=o.status, reason=o.reason) for o in outcomes]
    )

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.db import get_db
from app.errors import NotFoundError, ValidationError
from app.schemas.import_ import ImportBatchRead, ReviewQueueItemRead, ReviewResolveRequest
from app.services import categorization, imports as imports_service

router = APIRouter(prefix="/api/import", tags=["import"], dependencies=[Depends(require_api_key)])


@router.post("", response_model=ImportBatchRead, status_code=201)
async def import_qif(
    background_tasks: BackgroundTasks,
    account_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    content = (await file.read()).decode("utf-8", errors="replace")
    try:
        batch, imported_ids = imports_service.import_qif(
            db, account_id, file.filename or "import.qif", content
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    # Categorization must not block the import response (docs/requirements.md §2.4).
    # Runs in its own DB session — the request's `db` is closed by the time
    # background tasks run (see run_categorization_in_background docstring).
    background_tasks.add_task(categorization.run_categorization_in_background, imported_ids)
    return batch


@router.get("", response_model=list[ImportBatchRead])
def list_import_batches(db: Session = Depends(get_db)):
    return imports_service.list_import_batches(db)


@router.get("/{batch_id}", response_model=ImportBatchRead)
def get_import_batch(batch_id: int, db: Session = Depends(get_db)):
    try:
        return imports_service.get_import_batch(db, batch_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/review-queue/items", response_model=list[ReviewQueueItemRead])
def list_review_items(
    batch_id: int | None = None, pending_only: bool = True, db: Session = Depends(get_db)
):
    return imports_service.list_review_items(db, batch_id=batch_id, pending_only=pending_only)


@router.post("/review-queue/{item_id}/resolve", response_model=ReviewQueueItemRead)
def resolve_review_item(
    item_id: int,
    payload: ReviewResolveRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    try:
        item = imports_service.resolve_review_item(db, item_id, payload.action)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    if payload.action == "new":
        background_tasks.add_task(categorization.run_categorization_in_background, [])
    return item

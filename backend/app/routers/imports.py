from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.db import get_db
from app.errors import NotFoundError, ValidationError
from app.models.account import AccountType
from app.schemas.import_ import (
    DetectAccountsResponse,
    ImportBatchRead,
    ImportCommitRequest,
    ReviewQueueItemRead,
    ReviewResolveRequest,
)
from app.services import accounts as accounts_service, categorization, imports as imports_service

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


@router.post("/detect-accounts", response_model=DetectAccountsResponse)
async def detect_accounts(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = (await file.read()).decode("utf-8", errors="replace")
    has_sections, accounts = imports_service.detect_accounts(db, file.filename or "import", content)
    return DetectAccountsResponse(has_account_sections=has_sections, accounts=accounts)


@router.post("/commit", response_model=list[ImportBatchRead], status_code=201)
async def commit_import(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    resolutions: str = Form(...),
    db: Session = Depends(get_db),
):
    content = (await file.read()).decode("utf-8", errors="replace")
    try:
        payload = ImportCommitRequest.model_validate_json(resolutions)
    except PydanticValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    resolved: dict[str | None, int] = {}
    for r in payload.resolutions:
        if r.new_account is not None:
            account = accounts_service.create_account(
                db,
                name=r.new_account.name,
                type=AccountType(r.new_account.type),
                account_number=r.new_account.account_number,
                opening_balance=r.new_account.opening_balance,
                color=r.new_account.color,
            )
            resolved[r.parsed_name] = account.id
        elif r.account_id is not None:
            resolved[r.parsed_name] = r.account_id
        else:
            raise HTTPException(
                status_code=422,
                detail=f"Resolution for {r.parsed_name or 'this file'!r} needs an account_id or new_account",
            )

    try:
        batches, imported_ids = imports_service.import_multi(db, file.filename or "import", content, resolved)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    background_tasks.add_task(categorization.run_categorization_in_background, imported_ids)
    return batches


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

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.db import get_db
from app.errors import NotFoundError, ValidationError
from app.schemas.transaction import (
    SplitsUpdate,
    TransactionCreate,
    TransactionPage,
    TransactionRead,
    TransactionUpdate,
    TransferCreate,
)
from app.services import transactions as txn_service

router = APIRouter(
    prefix="/api/transactions", tags=["transactions"], dependencies=[Depends(require_api_key)]
)


@router.get("", response_model=TransactionPage)
def list_transactions(
    account_id: int | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    name_contains: str | None = None,
    category_id: int | None = None,
    page: int = 1,
    page_size: int = 100,
    db: Session = Depends(get_db),
):
    items, total = txn_service.list_transactions(
        db,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        amount_min=amount_min,
        amount_max=amount_max,
        name_contains=name_contains,
        category_id=category_id,
        page=page,
        page_size=page_size,
    )
    return TransactionPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/uncategorized-count")
def uncategorized_count(db: Session = Depends(get_db)):
    return {"count": txn_service.count_uncategorized(db)}


@router.post("", response_model=TransactionRead, status_code=201)
def create_transaction(payload: TransactionCreate, db: Session = Depends(get_db)):
    try:
        txn = txn_service.create_transaction(
            db,
            account_id=payload.account_id,
            date=payload.date,
            name=payload.name,
            splits=[(s.category_id, s.amount) for s in payload.splits],
        )
        return txn
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/transfer", response_model=list[TransactionRead], status_code=201)
def create_transfer(payload: TransferCreate, db: Session = Depends(get_db)):
    try:
        from_txn, to_txn = txn_service.create_transfer(
            db,
            from_account_id=payload.from_account_id,
            to_account_id=payload.to_account_id,
            date=payload.date,
            name=payload.name,
            amount=payload.amount,
        )
        return [from_txn, to_txn]
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/{transaction_id}", response_model=TransactionRead)
def get_transaction(transaction_id: int, db: Session = Depends(get_db)):
    try:
        return txn_service.get_transaction(db, transaction_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch("/{transaction_id}", response_model=TransactionRead)
def update_transaction(
    transaction_id: int, payload: TransactionUpdate, db: Session = Depends(get_db)
):
    try:
        return txn_service.update_transaction_details(
            db, transaction_id, date=payload.date, name=payload.name
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.put("/{transaction_id}/splits", response_model=TransactionRead)
def update_splits(transaction_id: int, payload: SplitsUpdate, db: Session = Depends(get_db)):
    try:
        return txn_service.update_transaction_splits(
            db, transaction_id, splits=[(s.category_id, s.amount) for s in payload.splits]
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.delete("/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    try:
        txn_service.delete_transaction(db, transaction_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

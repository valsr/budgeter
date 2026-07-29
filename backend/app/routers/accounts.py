from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.db import get_db
from app.errors import NotFoundError
from app.schemas.account import AccountCreate, AccountRead, AccountUpdate
from app.services import accounts as accounts_service
from app.services.balances import compute_balance, compute_balances

router = APIRouter(
    prefix="/api/accounts", tags=["accounts"], dependencies=[Depends(require_api_key)]
)


def _to_read(db: Session, account) -> AccountRead:
    balance = compute_balance(db, account.id, float(account.opening_balance))
    return AccountRead(
        id=account.id,
        name=account.name,
        account_number=account.account_number,
        type=account.type,
        opening_balance=float(account.opening_balance),
        color=account.color,
        balance=balance,
    )


@router.get("", response_model=list[AccountRead])
def list_accounts(db: Session = Depends(get_db)):
    accounts = accounts_service.list_accounts(db)
    activity = compute_balances(db, [a.id for a in accounts])
    return [
        AccountRead(
            id=a.id,
            name=a.name,
            account_number=a.account_number,
            type=a.type,
            opening_balance=float(a.opening_balance),
            color=a.color,
            balance=float(a.opening_balance) + activity[a.id],
        )
        for a in accounts
    ]


@router.post("", response_model=AccountRead, status_code=201)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)):
    account = accounts_service.create_account(
        db,
        name=payload.name,
        type=payload.type,
        account_number=payload.account_number,
        opening_balance=payload.opening_balance,
        color=payload.color,
    )
    return _to_read(db, account)


@router.get("/{account_id}", response_model=AccountRead)
def get_account(account_id: int, db: Session = Depends(get_db)):
    try:
        return _to_read(db, accounts_service.get_account(db, account_id))
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch("/{account_id}", response_model=AccountRead)
def update_account(account_id: int, payload: AccountUpdate, db: Session = Depends(get_db)):
    try:
        account = accounts_service.update_account(
            db,
            account_id,
            name=payload.name,
            type=payload.type,
            account_number=payload.account_number if "account_number" in payload.model_fields_set else ...,
            opening_balance=payload.opening_balance,
            color=payload.color,
        )
        return _to_read(db, account)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

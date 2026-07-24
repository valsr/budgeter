from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.db import get_db
from app.routers.budgets import row_to_read
from app.schemas.budget import ReportRowRead
from app.services import budgets as budgets_service

router = APIRouter(prefix="/api/overview", tags=["overview"], dependencies=[Depends(require_api_key)])


@router.get("", response_model=list[ReportRowRead])
def get_overview(year: int, through_month: int, db: Session = Depends(get_db)):
    if not (1 <= through_month <= 12):
        raise HTTPException(status_code=422, detail="through_month must be between 1 and 12")
    rows = budgets_service.get_overview(db, year, through_month)
    return [row_to_read(row) for row in rows]

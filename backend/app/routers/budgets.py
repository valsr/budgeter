from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.db import get_db
from app.errors import NotFoundError, ValidationError
from app.schemas.budget import (
    BudgetCreate,
    BudgetRead,
    BudgetUpdate,
    DroppedCategoryRead,
    MonthCell,
    ReportRowRead,
)
from app.services import budgets as budgets_service

router = APIRouter(prefix="/api/budgets", tags=["budgets"], dependencies=[Depends(require_api_key)])


def _categories_as_tuples(categories):
    return [(c.category_id, c.account_id, c.monthly_amounts) for c in categories]


def _saved_budget_read(budget, dropped) -> BudgetRead:
    """A save response also reports the categories the request listed that
    are no longer budgetable -- see budgets_service._partition_categories."""
    read = BudgetRead.model_validate(budget)
    read.dropped_categories = [
        DroppedCategoryRead(
            category_id=d.category_id, name=d.name, reason=d.reason, account_id=d.account_id
        )
        for d in dropped
    ]
    return read


def row_to_read(row) -> ReportRowRead:
    return ReportRowRead(
        row_key=row.row_key,
        category_id=row.category_id,
        account_id=row.account_id,
        name=row.name,
        is_parent=row.is_parent,
        monthly={m: MonthCell(budgeted=float(b), actual=float(a)) for m, (b, a) in row.monthly.items()},
        ytd_diff=float(row.ytd_diff),
        has_budget=row.has_budget,
        depth=row.depth,
        is_income=row.is_income,
    )


@router.get("", response_model=list[BudgetRead])
def list_budgets(db: Session = Depends(get_db)):
    return budgets_service.list_budgets(db)


@router.post("", response_model=BudgetRead, status_code=201)
def create_budget(payload: BudgetCreate, db: Session = Depends(get_db)):
    try:
        budget, dropped = budgets_service.create_budget(
            db, name=payload.name, categories=_categories_as_tuples(payload.categories), year=payload.year
        )
        return _saved_budget_read(budget, dropped)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/{budget_id}", response_model=BudgetRead)
def get_budget(budget_id: int, db: Session = Depends(get_db)):
    try:
        return budgets_service.get_budget(db, budget_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch("/{budget_id}", response_model=BudgetRead)
def update_budget(budget_id: int, payload: BudgetUpdate, db: Session = Depends(get_db)):
    try:
        budget, dropped = budgets_service.update_budget(
            db,
            budget_id,
            name=payload.name,
            categories=_categories_as_tuples(payload.categories) if payload.categories is not None else None,
            year=payload.year,
        )
        return _saved_budget_read(budget, dropped)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.delete("/{budget_id}", status_code=204)
def delete_budget(budget_id: int, db: Session = Depends(get_db)):
    try:
        budgets_service.delete_budget(db, budget_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{budget_id}/report", response_model=list[ReportRowRead])
def get_report(
    budget_id: int,
    year: int,
    through_month: int,
    account_id: Annotated[list[int] | None, Query()] = None,
    db: Session = Depends(get_db),
):
    """`account_id` may repeat, narrowing the report to those source accounts.
    Omit it for every account -- an empty selection isn't a distinct state,
    since a budget over no accounts has nothing to report."""
    if not (1 <= through_month <= 12):
        raise HTTPException(status_code=422, detail="through_month must be between 1 and 12")
    try:
        rows = budgets_service.get_report(
            db, budget_id, year, through_month, account_ids=account_id
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return [row_to_read(row) for row in rows]

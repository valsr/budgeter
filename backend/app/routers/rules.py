from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.db import get_db
from app.errors import NotFoundError, ValidationError
from app.schemas.rule import (
    RecategorizeRequest,
    RuleCreate,
    RuleRead,
    RuleReorderRequest,
    RuleSuggestionRead,
    RuleUpdate,
)
from app.services import categorization
from app.services import rules as rules_service

router = APIRouter(prefix="/api/rules", tags=["rules"], dependencies=[Depends(require_api_key)])


def _conditions_as_tuples(conditions):
    return [(c.field, c.operator, c.value) for c in conditions]


@router.get("", response_model=list[RuleRead])
def list_rules(db: Session = Depends(get_db)):
    return rules_service.list_rules(db)


@router.post("", response_model=RuleRead, status_code=201)
def create_rule(payload: RuleCreate, db: Session = Depends(get_db)):
    try:
        rule = rules_service.create_rule(
            db,
            match_type=payload.match_type,
            conditions=_conditions_as_tuples(payload.conditions),
            target_category_id=payload.target_category_id,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    # Creating a rule immediately re-triggers categorization against all
    # currently-uncategorized transactions (docs/requirements.md §3.1).
    categorization.run_categorization(db, None)
    db.refresh(rule)
    return rule


@router.get("/suggestions", response_model=list[RuleSuggestionRead])
def suggest_rules(threshold: int = rules_service.DEFAULT_SUGGESTION_THRESHOLD, db: Session = Depends(get_db)):
    return rules_service.suggest_new_rules(db, threshold=threshold)


@router.post("/recategorize")
def recategorize(payload: RecategorizeRequest, db: Session = Depends(get_db)):
    count = categorization.run_categorization(db, payload.transaction_ids)
    return {"suggested_count": count}


@router.get("/{rule_id}", response_model=RuleRead)
def get_rule(rule_id: int, db: Session = Depends(get_db)):
    try:
        return rules_service.get_rule(db, rule_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch("/{rule_id}", response_model=RuleRead)
def update_rule(rule_id: int, payload: RuleUpdate, db: Session = Depends(get_db)):
    try:
        rule = rules_service.update_rule(
            db,
            rule_id,
            match_type=payload.match_type,
            conditions=_conditions_as_tuples(payload.conditions) if payload.conditions is not None else None,
            target_category_id=payload.target_category_id,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    # Editing a rule also immediately re-triggers categorization.
    categorization.run_categorization(db, None)
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    try:
        rules_service.delete_rule(db, rule_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/reorder", response_model=list[RuleRead])
def reorder_rules(payload: RuleReorderRequest, db: Session = Depends(get_db)):
    try:
        return rules_service.reorder_rules(db, payload.ordered_ids)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

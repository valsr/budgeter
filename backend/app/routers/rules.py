from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.db import get_db
from app.errors import NotFoundError, ValidationError
from app.models.account import Account
from app.models.rule import ConditionField, MatchType
from app.schemas.rule import (
    LearnCheckRequest,
    LearnCheckResponse,
    LearnedRuleSuggestion,
    LearnRuleRequest,
    LearnRuleResponse,
    PreviewMatchesRequest,
    PreviewMatchesResponse,
    PreviewMatchItem,
    RecategorizeRequest,
    RuleConflictInfo,
    RuleCreate,
    RuleRead,
    RuleReorderRequest,
    RunPreviewItem,
    RunPreviewResponse,
    RuleUpdate,
)
from app.services import categorization
from app.services import rule_learning
from app.services import rules as rules_service
from app.services import transactions as txn_service
from app.services.rule_engine import Condition, RuleSpec, TransactionContext, evaluate_rule, find_matching_rule

router = APIRouter(prefix="/api/rules", tags=["rules"], dependencies=[Depends(require_api_key)])


def _conditions_as_tuples(conditions):
    return [(c.field, c.operator, c.value) for c in conditions]


def _summarize_rule(db: Session, rule: RuleSpec) -> str:
    """Human-readable one-liner for a rule, as shown in the learn-check
    conflict toast. An ACCOUNT condition's value is an account id, so it is
    resolved to the account's name rather than surfaced as a bare number."""

    def _value(condition: Condition) -> str:
        if condition.field == ConditionField.ACCOUNT:
            account = db.get(Account, int(condition.value)) if condition.value.isdigit() else None
            if account is not None:
                return account.name
        return condition.value

    joiner = " or " if rule.match_type == MatchType.ANY else " and "
    return joiner.join(
        f"{c.field.value} {c.operator.value} '{_value(c)}'" for c in rule.conditions
    )


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


@router.post("/recategorize")
def recategorize(payload: RecategorizeRequest, db: Session = Depends(get_db)):
    count = categorization.run_categorization(db, payload.transaction_ids)
    return {"suggested_count": count}


@router.get("/run-preview", response_model=RunPreviewResponse)
def run_preview(db: Session = Depends(get_db)):
    """Dry-run the current rule set against every eligible (uncategorized)
    transaction without persisting anything, so the UI can show what a
    "run rules" action would change before the user commits to it."""
    rule_specs = rules_service.rules_to_specs(rules_service.list_rules(db))
    pool = categorization.list_eligible_for_suggestion(db, None)

    items = []
    for txn in pool:
        split = categorization.find_uncategorized_split(txn)
        ctx = TransactionContext(date=txn.date, name=txn.name, account_id=txn.account_id, amount=float(split.amount))
        match = find_matching_rule(rule_specs, ctx)
        if match is None:
            continue
        items.append(
            RunPreviewItem(
                transaction_id=txn.id,
                date=txn.date,
                name=txn.name,
                account_id=txn.account_id,
                category_id=match.target_category_id,
                amount=float(split.amount),
            )
        )
    return RunPreviewResponse(items=items)


@router.post("/learn-check", response_model=LearnCheckResponse)
def learn_check(payload: LearnCheckRequest, db: Session = Depends(get_db)):
    try:
        txn = txn_service.get_transaction(db, payload.transaction_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    if len(txn.splits) != 1 or txn.splits[0].category_id is None:
        return LearnCheckResponse(status="none")

    split = txn.splits[0]
    ctx = TransactionContext(date=txn.date, name=txn.name, account_id=txn.account_id, amount=float(split.amount))
    rule_specs = rules_service.rules_to_specs(rules_service.list_rules(db))

    matched_rule = find_matching_rule(rule_specs, ctx)
    if matched_rule is not None:
        if matched_rule.target_category_id == split.category_id:
            return LearnCheckResponse(status="covered")
        return LearnCheckResponse(
            status="conflict",
            conflict=RuleConflictInfo(
                rule_id=matched_rule.id,
                rule_summary=_summarize_rule(db, matched_rule),
                matched_category_id=matched_rule.target_category_id,
                assigned_category_id=split.category_id,
            ),
        )

    # Note: no exclude_transaction_id here -- `txn` was just persisted with
    # this category, so it's already a genuine member of "transactions
    # categorized to split.category_id" and should count toward the sample
    # size threshold, not be treated as separate from it. The bar is "does
    # this category have enough data (this categorization plus its history)",
    # not "are there this many OTHER categorizations besides the one the
    # user just made."
    pool = rule_learning.find_learning_candidates(db, split.category_id)
    pool = rule_learning.filter_out_rule_matched(pool, rule_specs)
    candidate = rule_learning.learn_rule_for_category(db, pool, split.category_id)
    if candidate is None:
        return LearnCheckResponse(status="none")

    return LearnCheckResponse(
        status="suggestion",
        suggestion=LearnedRuleSuggestion(
            tier=candidate.tier,
            match_type=candidate.match_type,
            conditions=[{"field": c.field, "operator": c.operator, "value": c.value} for c in candidate.conditions],
            target_category_id=candidate.target_category_id,
        ),
    )


@router.post("/preview-matches", response_model=PreviewMatchesResponse)
def preview_matches(payload: PreviewMatchesRequest, db: Session = Depends(get_db)):
    spec = RuleSpec(
        id=-1,
        match_type=payload.match_type,
        priority=-1,
        target_category_id=payload.target_category_id,
        conditions=[Condition(field=c.field, operator=c.operator, value=c.value) for c in payload.conditions],
    )
    pool = categorization.list_eligible_for_suggestion(db, None)

    matches = []
    for txn in pool:
        split = categorization.find_uncategorized_split(txn)
        ctx = TransactionContext(date=txn.date, name=txn.name, account_id=txn.account_id, amount=float(split.amount))
        if evaluate_rule(spec, ctx):
            matches.append((txn, split))

    items = [PreviewMatchItem(id=t.id, date=t.date, name=t.name, amount=float(s.amount)) for t, s in matches]
    return PreviewMatchesResponse(count=len(items), matches=items)


@router.post("/learn", response_model=LearnRuleResponse, status_code=201)
def learn_rule(payload: LearnRuleRequest, db: Session = Depends(get_db)):
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

    # Learned rules get a one-time backfill (direct category_id assignment)
    # instead of the suggest-only pass plain rule creation triggers --
    # see rule_learning.confirm_matching_uncategorized.
    rule_spec = rules_service.rules_to_specs([rule])[0]
    confirmed = rule_learning.confirm_matching_uncategorized(db, rule_spec)
    db.refresh(rule)

    return LearnRuleResponse(
        rule=rule,
        confirmed_count=len(confirmed),
        confirmed_transaction_ids=[t.id for t in confirmed],
    )


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

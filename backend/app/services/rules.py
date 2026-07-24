from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.errors import NotFoundError, ValidationError
from app.models.category import Category
from app.models.rule import ConditionField, ConditionOperator, MatchType, Rule, RuleCondition
from app.models.split import Split
from app.models.transaction import Transaction, TransactionType
from app.services.dedupe import normalize_name
from app.services.rule_engine import Condition, RuleSpec, coerce_condition_value

ConditionInput = tuple[ConditionField, ConditionOperator, str]

DEFAULT_SUGGESTION_THRESHOLD = 3


def _get_rule_or_404(db: Session, rule_id: int) -> Rule:
    rule = db.get(Rule, rule_id)
    if rule is None:
        raise NotFoundError(f"Rule {rule_id} not found")
    return rule


def _validate_conditions(conditions: list[ConditionInput]) -> None:
    if not conditions:
        raise ValidationError("A rule must have at least one condition")
    for field, _operator, value in conditions:
        try:
            coerce_condition_value(field, value)
        except (ValueError, TypeError) as e:
            raise ValidationError(f"Invalid value {value!r} for field {field}") from e


def _next_priority(db: Session) -> int:
    max_priority = db.execute(select(Rule.priority).order_by(Rule.priority.desc())).scalars().first()
    return 0 if max_priority is None else max_priority + 1


def create_rule(
    db: Session,
    match_type: MatchType,
    conditions: list[ConditionInput],
    target_category_id: int,
    priority: int | None = None,
) -> Rule:
    if db.get(Category, target_category_id) is None:
        raise NotFoundError(f"Category {target_category_id} not found")
    _validate_conditions(conditions)

    rule = Rule(
        match_type=match_type,
        target_category_id=target_category_id,
        priority=priority if priority is not None else _next_priority(db),
    )
    rule.conditions = [
        RuleCondition(field=f, operator=o, value=v) for f, o, v in conditions
    ]
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def update_rule(
    db: Session,
    rule_id: int,
    match_type: MatchType | None = None,
    conditions: list[ConditionInput] | None = None,
    target_category_id: int | None = None,
) -> Rule:
    rule = _get_rule_or_404(db, rule_id)

    if target_category_id is not None:
        if db.get(Category, target_category_id) is None:
            raise NotFoundError(f"Category {target_category_id} not found")
        rule.target_category_id = target_category_id
    if match_type is not None:
        rule.match_type = match_type
    if conditions is not None:
        _validate_conditions(conditions)
        for c in list(rule.conditions):
            db.delete(c)
        rule.conditions = [
            RuleCondition(field=f, operator=o, value=v) for f, o, v in conditions
        ]

    db.commit()
    db.refresh(rule)
    return rule


def delete_rule(db: Session, rule_id: int) -> None:
    rule = _get_rule_or_404(db, rule_id)
    db.delete(rule)
    db.commit()


def reorder_rules(db: Session, ordered_ids: list[int]) -> list[Rule]:
    rules = list(db.execute(select(Rule)).scalars().all())
    rule_ids = {r.id for r in rules}
    if rule_ids != set(ordered_ids):
        raise ValidationError("ordered_ids must contain exactly the current rule set")

    by_id = {r.id: r for r in rules}
    for index, rule_id in enumerate(ordered_ids):
        by_id[rule_id].priority = index
    db.commit()
    return [by_id[rule_id] for rule_id in ordered_ids]


def list_rules(db: Session) -> list[Rule]:
    stmt = (
        select(Rule)
        .options(selectinload(Rule.conditions))
        .order_by(Rule.priority)
    )
    return list(db.execute(stmt).scalars().all())


def get_rule(db: Session, rule_id: int) -> Rule:
    return _get_rule_or_404(db, rule_id)


def rules_to_specs(rules: list[Rule]) -> list[RuleSpec]:
    return [
        RuleSpec(
            id=r.id,
            match_type=r.match_type,
            priority=r.priority,
            target_category_id=r.target_category_id,
            conditions=[
                Condition(field=c.field, operator=c.operator, value=c.value) for c in r.conditions
            ],
        )
        for r in rules
    ]


def suggest_new_rules(
    db: Session, threshold: int = DEFAULT_SUGGESTION_THRESHOLD
) -> list[dict]:
    """Mine confirmed categorizations for repeating (merchant, category)
    patterns and propose new rules once a repetition threshold is met.
    """
    rows = db.execute(
        select(Transaction.name, Split.category_id)
        .join(Split, Split.transaction_id == Transaction.id)
        .where(Transaction.type == TransactionType.NORMAL)
        .where(Split.category_id.is_not(None))
    ).all()

    counts: Counter[tuple[str, int]] = Counter()
    samples: dict[tuple[str, int], str] = {}
    for name, category_id in rows:
        key = (normalize_name(name), category_id)
        counts[key] += 1
        samples.setdefault(key, name)

    existing_rules = list_rules(db)
    existing_signatures = {
        (r.match_type, tuple(sorted((c.field, c.operator, c.value) for c in r.conditions)), r.target_category_id)
        for r in existing_rules
    }

    suggestions = []
    for (normalized_name, category_id), count in counts.items():
        if count < threshold:
            continue
        signature = (
            MatchType.ALL,
            ((ConditionField.NAME, ConditionOperator.CONTAINS, normalized_name),),
            category_id,
        )
        if signature in existing_signatures:
            continue
        suggestions.append(
            {
                "match_type": MatchType.ALL,
                "conditions": [
                    {
                        "field": ConditionField.NAME,
                        "operator": ConditionOperator.CONTAINS,
                        "value": normalized_name,
                    }
                ],
                "target_category_id": category_id,
                "occurrence_count": count,
                "sample_name": samples[(normalized_name, category_id)],
            }
        )

    suggestions.sort(key=lambda s: s["occurrence_count"], reverse=True)
    return suggestions

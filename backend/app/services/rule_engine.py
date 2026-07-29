import datetime as dt
from dataclasses import dataclass

from app.models.rule import ConditionField, ConditionOperator, MatchType
from app.services.dedupe import normalize_name


@dataclass
class TransactionContext:
    date: dt.date
    name: str
    account_id: int
    amount: float


@dataclass
class Condition:
    field: ConditionField
    operator: ConditionOperator
    value: str


@dataclass
class RuleSpec:
    id: int
    match_type: MatchType
    priority: int
    target_category_id: int
    conditions: list[Condition]


def _field_value(field: ConditionField, ctx: TransactionContext):
    if field == ConditionField.DATE:
        return ctx.date
    if field == ConditionField.DAY_OF_MONTH:
        return ctx.date.day
    if field == ConditionField.NAME:
        return ctx.name
    if field == ConditionField.ACCOUNT:
        return ctx.account_id
    if field == ConditionField.AMOUNT:
        return ctx.amount
    raise ValueError(f"Unknown condition field: {field}")


def coerce_condition_value(field: ConditionField, raw: str):
    if field == ConditionField.DATE:
        return dt.date.fromisoformat(raw)
    if field == ConditionField.DAY_OF_MONTH:
        return int(raw)
    if field == ConditionField.ACCOUNT:
        return int(raw)
    if field == ConditionField.AMOUNT:
        return float(raw)
    return raw  # NAME: plain string


def evaluate_condition(condition: Condition, ctx: TransactionContext) -> bool:
    actual = _field_value(condition.field, ctx)
    expected = coerce_condition_value(condition.field, condition.value)

    if condition.operator == ConditionOperator.CONTAINS:
        if condition.field == ConditionField.NAME:
            # Rule learning derives its NAME value from normalize_name'd
            # merchant strings (punctuation stripped, e.g. "GITHUB, INC."
            # -> "github inc") so it can find a substring common to
            # differently-punctuated variants. Matching must normalize the
            # same way, or a learned value never matches the raw names it
            # was learned from.
            return normalize_name(str(expected)) in normalize_name(str(actual))
        return str(expected).lower() in str(actual).lower()
    if condition.operator == ConditionOperator.NOT_CONTAINS:
        if condition.field == ConditionField.NAME:
            return normalize_name(str(expected)) not in normalize_name(str(actual))
        return str(expected).lower() not in str(actual).lower()
    if condition.operator == ConditionOperator.EQUALS:
        return actual == expected
    if condition.operator == ConditionOperator.LESS_THAN:
        return actual < expected
    if condition.operator == ConditionOperator.GREATER_THAN:
        return actual > expected
    raise ValueError(f"Unknown condition operator: {condition.operator}")


def evaluate_rule(rule: RuleSpec, ctx: TransactionContext) -> bool:
    if not rule.conditions:
        return False
    results = (evaluate_condition(c, ctx) for c in rule.conditions)
    return any(results) if rule.match_type == MatchType.ANY else all(results)


def find_matching_rule(rules: list[RuleSpec], ctx: TransactionContext) -> RuleSpec | None:
    """First-match-wins: `rules` must already be ordered by priority."""
    for rule in rules:
        if evaluate_rule(rule, ctx):
            return rule
    return None

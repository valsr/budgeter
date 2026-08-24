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
        # Sign-agnostic: a $50 withdrawal and a $50 deposit both satisfy
        # "amount greater_than 40" -- direction is checked separately via
        # the IS_DEPOSIT/IS_WITHDRAWAL operators, not by field comparison.
        return abs(ctx.amount)
    raise ValueError(f"Unknown condition field: {field}")


_DIRECTION_OPERATORS = {ConditionOperator.IS_DEPOSIT, ConditionOperator.IS_WITHDRAWAL}

# The account field identifies accounts by surrogate id, so substring and
# ordering comparisons on it are meaningless. Set membership is the only
# operation that makes sense -- and "one of these accounts" is what people
# actually want to express, so IN/NOT_IN replace EQUALS rather than
# supplementing it.
MEMBERSHIP_OPERATORS = {ConditionOperator.IN, ConditionOperator.NOT_IN}


def operator_needs_value(operator: ConditionOperator) -> bool:
    """False for is_deposit/is_withdrawal, which match on the split's sign
    alone and ignore the condition's value entirely -- callers that validate
    or coerce a condition's value (e.g. rules.py's _validate_conditions)
    should skip those checks for such operators rather than reject an
    intentionally-empty value."""
    return operator not in _DIRECTION_OPERATORS


def coerce_condition_value(field: ConditionField, raw: str):
    if field == ConditionField.DATE:
        return dt.date.fromisoformat(raw)
    if field == ConditionField.DAY_OF_MONTH:
        return int(raw)
    if field == ConditionField.ACCOUNT:
        return parse_account_ids(raw)
    if field == ConditionField.AMOUNT:
        return float(raw)
    return raw  # NAME: plain string


def parse_account_ids(raw: str) -> frozenset[int]:
    """An account condition's value is a comma-separated list of account ids
    ("3" or "3,7"). A single id stays a valid one-element list, so conditions
    written before IN/NOT_IN existed parse unchanged."""
    ids = frozenset(int(part) for part in raw.split(",") if part.strip())
    if not ids:
        raise ValueError("An account condition must name at least one account")
    return ids


def format_account_ids(ids: list[int]) -> str:
    """The storage form of an account condition's value -- sorted so two
    conditions naming the same accounts compare equal as strings."""
    return ",".join(str(i) for i in sorted(set(ids)))


def evaluate_condition(condition: Condition, ctx: TransactionContext) -> bool:
    # These two check the split's raw sign directly and ignore the
    # condition's value entirely, so they must run before the
    # abs()'d _field_value/coerce_condition_value pair below.
    if condition.operator == ConditionOperator.IS_DEPOSIT:
        return ctx.amount > 0
    if condition.operator == ConditionOperator.IS_WITHDRAWAL:
        return ctx.amount < 0

    actual = _field_value(condition.field, ctx)
    expected = coerce_condition_value(condition.field, condition.value)

    if condition.operator == ConditionOperator.IN:
        return actual in expected
    if condition.operator == ConditionOperator.NOT_IN:
        return actual not in expected
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

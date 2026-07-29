import datetime as dt

import pytest

from app.models.rule import ConditionField, ConditionOperator, MatchType
from app.services.rule_engine import (
    Condition,
    RuleSpec,
    TransactionContext,
    evaluate_condition,
    evaluate_rule,
    find_matching_rule,
)


def ctx(**overrides):
    defaults = dict(date=dt.date(2026, 7, 19), name="GITHUB INC", account_id=1, amount=-21.00)
    defaults.update(overrides)
    return TransactionContext(**defaults)


class TestEvaluateCondition:
    def test_name_contains_case_insensitive(self):
        c = Condition(ConditionField.NAME, ConditionOperator.CONTAINS, "github")
        assert evaluate_condition(c, ctx()) is True

    def test_name_contains_no_match(self):
        c = Condition(ConditionField.NAME, ConditionOperator.CONTAINS, "spotify")
        assert evaluate_condition(c, ctx()) is False

    def test_name_not_contains(self):
        c = Condition(ConditionField.NAME, ConditionOperator.NOT_CONTAINS, "spotify")
        assert evaluate_condition(c, ctx()) is True

    def test_name_contains_ignores_punctuation_differences(self):
        # rule_learning derives NAME values from normalize_name'd (punctuation
        # stripped) merchant strings, e.g. "GITHUB, INC." -> "github inc" --
        # matching must normalize the same way or a learned value never
        # matches the raw names it was learned from.
        c = Condition(ConditionField.NAME, ConditionOperator.CONTAINS, "github inc")
        assert evaluate_condition(c, ctx(name="GITHUB, INC.")) is True

    def test_name_not_contains_ignores_punctuation_differences(self):
        c = Condition(ConditionField.NAME, ConditionOperator.NOT_CONTAINS, "github inc")
        assert evaluate_condition(c, ctx(name="GITHUB, INC.")) is False

    def test_name_equals(self):
        c = Condition(ConditionField.NAME, ConditionOperator.EQUALS, "GITHUB INC")
        assert evaluate_condition(c, ctx()) is True

    def test_amount_equals(self):
        c = Condition(ConditionField.AMOUNT, ConditionOperator.EQUALS, "-21.00")
        assert evaluate_condition(c, ctx()) is True

    def test_amount_less_than(self):
        c = Condition(ConditionField.AMOUNT, ConditionOperator.LESS_THAN, "0")
        assert evaluate_condition(c, ctx()) is True

    def test_amount_greater_than(self):
        c = Condition(ConditionField.AMOUNT, ConditionOperator.GREATER_THAN, "-100")
        assert evaluate_condition(c, ctx()) is True

    def test_date_equals(self):
        c = Condition(ConditionField.DATE, ConditionOperator.EQUALS, "2026-07-19")
        assert evaluate_condition(c, ctx()) is True

    def test_date_less_than(self):
        c = Condition(ConditionField.DATE, ConditionOperator.LESS_THAN, "2026-08-01")
        assert evaluate_condition(c, ctx()) is True

    def test_date_greater_than(self):
        c = Condition(ConditionField.DATE, ConditionOperator.GREATER_THAN, "2026-07-01")
        assert evaluate_condition(c, ctx()) is True

    def test_day_of_month_equals(self):
        c = Condition(ConditionField.DAY_OF_MONTH, ConditionOperator.EQUALS, "19")
        assert evaluate_condition(c, ctx()) is True

    def test_day_of_month_less_than(self):
        c = Condition(ConditionField.DAY_OF_MONTH, ConditionOperator.LESS_THAN, "20")
        assert evaluate_condition(c, ctx()) is True

    def test_day_of_month_greater_than(self):
        c = Condition(ConditionField.DAY_OF_MONTH, ConditionOperator.GREATER_THAN, "1")
        assert evaluate_condition(c, ctx()) is True

    def test_account_equals(self):
        c = Condition(ConditionField.ACCOUNT, ConditionOperator.EQUALS, "1")
        assert evaluate_condition(c, ctx(account_id=1)) is True
        assert evaluate_condition(c, ctx(account_id=2)) is False


class TestEvaluateRule:
    def test_all_requires_every_condition(self):
        rule = RuleSpec(
            id=1,
            match_type=MatchType.ALL,
            priority=0,
            target_category_id=1,
            conditions=[
                Condition(ConditionField.NAME, ConditionOperator.CONTAINS, "github"),
                Condition(ConditionField.AMOUNT, ConditionOperator.LESS_THAN, "0"),
            ],
        )
        assert evaluate_rule(rule, ctx()) is True
        assert evaluate_rule(rule, ctx(amount=50)) is False

    def test_any_requires_one_condition(self):
        rule = RuleSpec(
            id=1,
            match_type=MatchType.ANY,
            priority=0,
            target_category_id=1,
            conditions=[
                Condition(ConditionField.NAME, ConditionOperator.CONTAINS, "spotify"),
                Condition(ConditionField.NAME, ConditionOperator.CONTAINS, "github"),
            ],
        )
        assert evaluate_rule(rule, ctx()) is True

    def test_any_false_when_none_match(self):
        rule = RuleSpec(
            id=1,
            match_type=MatchType.ANY,
            priority=0,
            target_category_id=1,
            conditions=[
                Condition(ConditionField.NAME, ConditionOperator.CONTAINS, "spotify"),
                Condition(ConditionField.NAME, ConditionOperator.CONTAINS, "uber"),
            ],
        )
        assert evaluate_rule(rule, ctx()) is False

    def test_rule_with_no_conditions_never_matches(self):
        rule = RuleSpec(id=1, match_type=MatchType.ALL, priority=0, target_category_id=1, conditions=[])
        assert evaluate_rule(rule, ctx()) is False


class TestFindMatchingRule:
    def test_first_match_wins(self):
        rule_a = RuleSpec(
            id=1,
            match_type=MatchType.ALL,
            priority=0,
            target_category_id=10,
            conditions=[Condition(ConditionField.NAME, ConditionOperator.CONTAINS, "github")],
        )
        rule_b = RuleSpec(
            id=2,
            match_type=MatchType.ALL,
            priority=1,
            target_category_id=20,
            conditions=[Condition(ConditionField.NAME, ConditionOperator.CONTAINS, "git")],
        )
        # both match "GITHUB INC"; the one ordered first should win
        match = find_matching_rule([rule_a, rule_b], ctx())
        assert match.id == 1

        match_reversed = find_matching_rule([rule_b, rule_a], ctx())
        assert match_reversed.id == 2

    def test_no_match_returns_none(self):
        rule = RuleSpec(
            id=1,
            match_type=MatchType.ALL,
            priority=0,
            target_category_id=1,
            conditions=[Condition(ConditionField.NAME, ConditionOperator.CONTAINS, "spotify")],
        )
        assert find_matching_rule([rule], ctx()) is None

    def test_empty_rule_list_returns_none(self):
        assert find_matching_rule([], ctx()) is None


@pytest.mark.parametrize(
    "field,raw,error",
    [
        (ConditionField.DATE, "not-a-date", ValueError),
        (ConditionField.DAY_OF_MONTH, "abc", ValueError),
        (ConditionField.ACCOUNT, "abc", ValueError),
        (ConditionField.AMOUNT, "abc", ValueError),
    ],
)
def test_invalid_condition_values_raise(field, raw, error):
    from app.services.rule_engine import coerce_condition_value

    with pytest.raises(error):
        coerce_condition_value(field, raw)

import pytest

from app.errors import NotFoundError, ValidationError
from app.models.rule import ConditionField, ConditionOperator, MatchType
from app.services import categories as categories_svc
from app.services import rules as rules_svc


@pytest.fixture()
def category(db_session):
    return categories_svc.create_category(db_session, "personal")


def test_create_rule(db_session, category):
    rule = rules_svc.create_rule(
        db_session,
        MatchType.ALL,
        [(ConditionField.NAME, ConditionOperator.CONTAINS, "GITHUB")],
        category.id,
    )
    assert rule.id is not None
    assert rule.priority == 0
    assert len(rule.conditions) == 1


def test_create_rule_unknown_category_404(db_session):
    with pytest.raises(NotFoundError):
        rules_svc.create_rule(
            db_session, MatchType.ALL, [(ConditionField.NAME, ConditionOperator.CONTAINS, "x")], 999
        )


def test_create_rule_no_conditions_rejected(db_session, category):
    with pytest.raises(ValidationError):
        rules_svc.create_rule(db_session, MatchType.ALL, [], category.id)


def test_create_rule_invalid_condition_value_rejected(db_session, category):
    with pytest.raises(ValidationError):
        rules_svc.create_rule(
            db_session, MatchType.ALL, [(ConditionField.AMOUNT, ConditionOperator.EQUALS, "not-a-number")], category.id
        )


def test_priority_increments_across_rules(db_session, category):
    r1 = rules_svc.create_rule(
        db_session, MatchType.ALL, [(ConditionField.NAME, ConditionOperator.CONTAINS, "a")], category.id
    )
    r2 = rules_svc.create_rule(
        db_session, MatchType.ALL, [(ConditionField.NAME, ConditionOperator.CONTAINS, "b")], category.id
    )
    assert r1.priority == 0
    assert r2.priority == 1


def test_update_rule_conditions_and_target(db_session, category):
    other = categories_svc.create_category(db_session, "shared")
    rule = rules_svc.create_rule(
        db_session, MatchType.ALL, [(ConditionField.NAME, ConditionOperator.CONTAINS, "a")], category.id
    )
    updated = rules_svc.update_rule(
        db_session,
        rule.id,
        conditions=[(ConditionField.NAME, ConditionOperator.CONTAINS, "b")],
        target_category_id=other.id,
    )
    assert updated.target_category_id == other.id
    assert len(updated.conditions) == 1
    assert updated.conditions[0].value == "b"


def test_update_rule_match_type_only(db_session, category):
    rule = rules_svc.create_rule(
        db_session, MatchType.ALL, [(ConditionField.NAME, ConditionOperator.CONTAINS, "a")], category.id
    )
    updated = rules_svc.update_rule(db_session, rule.id, match_type=MatchType.ANY)
    assert updated.match_type == MatchType.ANY


def test_update_rule_missing_404(db_session):
    with pytest.raises(NotFoundError):
        rules_svc.update_rule(db_session, 999, match_type=MatchType.ANY)


def test_update_rule_unknown_category_404(db_session, category):
    rule = rules_svc.create_rule(
        db_session, MatchType.ALL, [(ConditionField.NAME, ConditionOperator.CONTAINS, "a")], category.id
    )
    with pytest.raises(NotFoundError):
        rules_svc.update_rule(db_session, rule.id, target_category_id=999)


def test_update_rule_bad_conditions_rejected(db_session, category):
    rule = rules_svc.create_rule(
        db_session, MatchType.ALL, [(ConditionField.NAME, ConditionOperator.CONTAINS, "a")], category.id
    )
    with pytest.raises(ValidationError):
        rules_svc.update_rule(db_session, rule.id, conditions=[])


def test_delete_rule(db_session, category):
    rule = rules_svc.create_rule(
        db_session, MatchType.ALL, [(ConditionField.NAME, ConditionOperator.CONTAINS, "a")], category.id
    )
    rules_svc.delete_rule(db_session, rule.id)
    with pytest.raises(NotFoundError):
        rules_svc.get_rule(db_session, rule.id)


def test_delete_rule_missing_404(db_session):
    with pytest.raises(NotFoundError):
        rules_svc.delete_rule(db_session, 999)


def test_reorder_rules(db_session, category):
    r1 = rules_svc.create_rule(
        db_session, MatchType.ALL, [(ConditionField.NAME, ConditionOperator.CONTAINS, "a")], category.id
    )
    r2 = rules_svc.create_rule(
        db_session, MatchType.ALL, [(ConditionField.NAME, ConditionOperator.CONTAINS, "b")], category.id
    )
    reordered = rules_svc.reorder_rules(db_session, [r2.id, r1.id])
    assert [r.id for r in reordered] == [r2.id, r1.id]
    assert reordered[0].priority == 0
    assert reordered[1].priority == 1


def test_reorder_rules_rejects_mismatched_ids(db_session, category):
    r1 = rules_svc.create_rule(
        db_session, MatchType.ALL, [(ConditionField.NAME, ConditionOperator.CONTAINS, "a")], category.id
    )
    with pytest.raises(ValidationError):
        rules_svc.reorder_rules(db_session, [r1.id, 999])


def test_list_rules_ordered_by_priority(db_session, category):
    r1 = rules_svc.create_rule(
        db_session, MatchType.ALL, [(ConditionField.NAME, ConditionOperator.CONTAINS, "a")], category.id
    )
    r2 = rules_svc.create_rule(
        db_session, MatchType.ALL, [(ConditionField.NAME, ConditionOperator.CONTAINS, "b")], category.id
    )
    rules_svc.reorder_rules(db_session, [r2.id, r1.id])
    listed = rules_svc.list_rules(db_session)
    assert [r.id for r in listed] == [r2.id, r1.id]


def test_get_rule_missing_404(db_session):
    with pytest.raises(NotFoundError):
        rules_svc.get_rule(db_session, 999)


def test_rules_to_specs_roundtrip(db_session, category):
    rule = rules_svc.create_rule(
        db_session, MatchType.ALL, [(ConditionField.NAME, ConditionOperator.CONTAINS, "a")], category.id
    )
    specs = rules_svc.rules_to_specs([rule])
    assert specs[0].id == rule.id
    assert specs[0].conditions[0].value == "a"

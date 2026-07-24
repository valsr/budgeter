from pydantic import BaseModel, ConfigDict

from app.models.rule import ConditionField, ConditionOperator, MatchType


class ConditionSchema(BaseModel):
    field: ConditionField
    operator: ConditionOperator
    value: str


class ConditionRead(ConditionSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int


class RuleCreate(BaseModel):
    match_type: MatchType
    conditions: list[ConditionSchema]
    target_category_id: int


class RuleUpdate(BaseModel):
    match_type: MatchType | None = None
    conditions: list[ConditionSchema] | None = None
    target_category_id: int | None = None


class RuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    match_type: MatchType
    priority: int
    target_category_id: int
    conditions: list[ConditionRead]


class RuleReorderRequest(BaseModel):
    ordered_ids: list[int]


class RuleSuggestionRead(BaseModel):
    match_type: MatchType
    conditions: list[ConditionSchema]
    target_category_id: int
    occurrence_count: int
    sample_name: str


class RecategorizeRequest(BaseModel):
    transaction_ids: list[int] | None = None

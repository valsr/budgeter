import datetime as dt
from typing import Literal

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


class RecategorizeRequest(BaseModel):
    transaction_ids: list[int] | None = None


class LearnCheckRequest(BaseModel):
    transaction_id: int


class RuleConflictInfo(BaseModel):
    rule_id: int
    rule_summary: str
    matched_category_id: int
    assigned_category_id: int


class LearnedRuleSuggestion(BaseModel):
    tier: int
    match_type: MatchType
    conditions: list[ConditionSchema]
    target_category_id: int


class LearnCheckResponse(BaseModel):
    status: Literal["covered", "conflict", "suggestion", "none"]
    conflict: RuleConflictInfo | None = None
    suggestion: LearnedRuleSuggestion | None = None


class PreviewMatchesRequest(BaseModel):
    match_type: MatchType
    conditions: list[ConditionSchema]
    target_category_id: int


class PreviewMatchSample(BaseModel):
    id: int
    date: dt.date
    name: str
    amount: float


class PreviewMatchesResponse(BaseModel):
    count: int
    sample: list[PreviewMatchSample]


class LearnRuleRequest(BaseModel):
    match_type: MatchType
    conditions: list[ConditionSchema]
    target_category_id: int


class LearnRuleResponse(BaseModel):
    rule: RuleRead
    confirmed_count: int
    confirmed_transaction_ids: list[int]

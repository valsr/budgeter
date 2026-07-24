from pydantic import BaseModel


class AiSuggestionInputSchema(BaseModel):
    transaction_id: int
    split_id: int
    category_id: int


class AiSuggestRequest(BaseModel):
    suggestions: list[AiSuggestionInputSchema]


class AiSuggestResponse(BaseModel):
    applied: int
    skipped: list[int]

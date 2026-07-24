from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.db import get_db
from app.errors import NotFoundError
from app.schemas.ai import AiSuggestRequest, AiSuggestResponse
from app.schemas.transaction import TransactionRead
from app.services import ai_categorization

router = APIRouter(prefix="/api/ai", tags=["ai"], dependencies=[Depends(require_api_key)])


@router.get("/uncategorized", response_model=list[TransactionRead])
def list_uncategorized(db: Session = Depends(get_db)):
    return ai_categorization.list_uncategorized_for_ai(db)


@router.post("/suggest", response_model=AiSuggestResponse)
def suggest(payload: AiSuggestRequest, db: Session = Depends(get_db)):
    try:
        result = ai_categorization.apply_ai_suggestions(
            db,
            [
                ai_categorization.AiSuggestionInput(
                    transaction_id=s.transaction_id, split_id=s.split_id, category_id=s.category_id
                )
                for s in payload.suggestions
            ],
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return AiSuggestResponse(applied=result.applied, skipped=result.skipped)

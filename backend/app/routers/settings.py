from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.db import get_db
from app.schemas.api_key import ApiKeyRead
from app.services import api_key as api_key_service

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(require_api_key)])


@router.get("/api-key", response_model=ApiKeyRead)
def get_api_key(db: Session = Depends(get_db)):
    return ApiKeyRead(api_key=api_key_service.get_current_key(db))


@router.post("/api-key/regenerate", response_model=ApiKeyRead)
def regenerate_api_key(db: Session = Depends(get_db)):
    return ApiKeyRead(api_key=api_key_service.regenerate_key(db))

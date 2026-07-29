from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.db import get_db
from app.errors import ValidationError
from app.schemas.api_key import ApiKeyRead
from app.schemas.settings import RetentionSettings
from app.services import api_key as api_key_service
from app.services import app_settings as app_settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(require_api_key)])


@router.get("/api-key", response_model=ApiKeyRead)
def get_api_key(db: Session = Depends(get_db)):
    return ApiKeyRead(api_key=api_key_service.get_current_key(db))


@router.post("/api-key/regenerate", response_model=ApiKeyRead)
def regenerate_api_key(db: Session = Depends(get_db)):
    return ApiKeyRead(api_key=api_key_service.regenerate_key(db))


@router.get("/retention", response_model=RetentionSettings)
def get_retention(db: Session = Depends(get_db)):
    return RetentionSettings(retention_days=app_settings_service.get_retention_days(db))


@router.patch("/retention", response_model=RetentionSettings)
def update_retention(payload: RetentionSettings, db: Session = Depends(get_db)):
    try:
        days = app_settings_service.set_retention_days(db, payload.retention_days)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return RetentionSettings(retention_days=days)

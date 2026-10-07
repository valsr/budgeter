from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.errors import ValidationError
from app.schemas.auth import ApiKeyReveal, ApiKeyStatus
from app.schemas.settings import RetentionSettings
from app.server_db import get_server_db
from app.server_models import User
from app.services import app_settings as app_settings_service
from app.services import users as users_service

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(current_user)])


@router.get("/api-key", response_model=ApiKeyStatus)
def get_api_key(user: User = Depends(current_user)):
    # Only whether one exists: the key is stored hashed and can't be shown again.
    return ApiKeyStatus(has_key=user.api_key_hash is not None)


@router.post("/api-key/regenerate", response_model=ApiKeyReveal)
def regenerate_api_key(user: User = Depends(current_user), sdb: Session = Depends(get_server_db)):
    return ApiKeyReveal(api_key=users_service.regenerate_api_key(sdb, user))


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

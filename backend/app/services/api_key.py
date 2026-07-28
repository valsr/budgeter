import datetime as dt
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.api_key import ApiKey


def get_current_key(db: Session) -> str:
    row = db.execute(select(ApiKey)).scalars().first()
    return row.key if row is not None else settings.api_key


def regenerate_key(db: Session) -> str:
    new_key = secrets.token_urlsafe(32)
    row = db.execute(select(ApiKey)).scalars().first()
    now = dt.datetime.now(dt.timezone.utc)
    if row is None:
        db.add(ApiKey(key=new_key, updated_at=now))
    else:
        row.key = new_key
        row.updated_at = now
    db.commit()
    return new_key

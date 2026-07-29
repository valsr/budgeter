import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ValidationError
from app.models.change import AppSettings

DEFAULT_RETENTION_DAYS = 100
MIN_RETENTION_DAYS = 1
MAX_RETENTION_DAYS = 3650


def get_retention_days(db: Session) -> int:
    row = db.execute(select(AppSettings)).scalars().first()
    return row.retention_days if row is not None else DEFAULT_RETENTION_DAYS


def set_retention_days(db: Session, days: int) -> int:
    if not (MIN_RETENTION_DAYS <= days <= MAX_RETENTION_DAYS):
        raise ValidationError(
            f"Retention must be between {MIN_RETENTION_DAYS} and {MAX_RETENTION_DAYS} days"
        )

    row = db.execute(select(AppSettings)).scalars().first()
    now = dt.datetime.now(dt.timezone.utc)
    if row is None:
        db.add(AppSettings(retention_days=days, updated_at=now))
    else:
        row.retention_days = days
        row.updated_at = now
    db.commit()

    from app.services.change_log import purge_expired

    purge_expired(db)
    return days

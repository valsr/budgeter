from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ApiKey(Base):
    """Single-row table holding the shared bearer secret (docs/requirements.md §6).

    Absence of a row is a valid state (fresh test DBs, pre-migration installs)
    — app/services/api_key.py falls back to the BUDGETER_API_KEY env default
    in that case, so a row only needs to exist once the key is regenerated.
    """

    __tablename__ = "api_key"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

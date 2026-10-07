from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.server_db import ServerBase


def utcnow() -> datetime:
    """Naive UTC. SQLite hands datetimes back without a zone whatever went
    in, so everything in the server database stays naive UTC throughout
    rather than mixing aware and naive values in comparisons."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(ServerBase):
    __tablename__ = "users"
    # AUTOINCREMENT: an id is never handed out twice. Without it SQLite
    # reuses the id of the most recently deleted user, and with the id go
    # whatever still points at it -- a session created by a login that raced
    # the delete, a stranded books file.
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    """Stored trimmed and lower-cased -- see services/users.normalize_username."""
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    """Every account is an admin unless another admin says otherwise."""
    is_disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    api_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    """SHA-256 of the user's bearer key; the key itself is shown once and never stored."""
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class UserSession(ServerBase):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ServerSettings(ServerBase):
    """Single-row table; services/users.get_settings creates the row on first use."""

    __tablename__ = "server_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    legacy_books_claimed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    """Set once the pre-accounts database has been copied to a user, so it
    is never handed out twice (see books.claim_legacy_books)."""

    # How the launcher (app/serve.py) serves the app. Read once at startup:
    # changing any of these takes a restart. See services/server_config.py.
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=8000, server_default="8000")
    ssl_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    ssl_certfile: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    ssl_keyfile: Mapped[str | None] = mapped_column(String(1000), nullable=True)

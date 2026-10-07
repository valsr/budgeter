from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore": a .env left over from the single-user days may still set
    # BUDGETER_API_KEY, which no longer means anything (keys are per user now).
    model_config = SettingsConfigDict(env_prefix="BUDGETER_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./budgeter.db"
    """Where the pre-accounts, single-user database lives. It is only ever
    read: the first registered user gets a copy of it (see app/books.py)."""
    host: str = "127.0.0.1"
    """Interface the launcher (app/serve.py) binds. The container sets 0.0.0.0."""
    port: int | None = None
    """Overrides the port saved in Settings → Server -- for when the port is
    dictated from outside, e.g. a container's published port mapping."""
    ssl_disabled: bool = False
    """Escape hatch: start on plain HTTP even though SSL is enabled in Settings → Server."""
    data_dir: str | None = None
    """Holds server.db and books/<user_id>.db. Defaults to the directory of
    the database_url file -- see resolve_data_dir."""


settings = Settings()


_SQLITE_FILE_PREFIX = "sqlite:///"


def legacy_database_path() -> Path | None:
    """The file database_url names, or None for the in-memory sentinel."""
    url = settings.database_url
    if not url.startswith(_SQLITE_FILE_PREFIX):
        return None
    return Path(url[len(_SQLITE_FILE_PREFIX):]).resolve()


def resolve_data_dir() -> Path | None:
    """The directory holding server.db and the per-user books files."""
    if settings.data_dir:
        return Path(settings.data_dir)
    legacy = legacy_database_path()
    return legacy.parent if legacy is not None else None

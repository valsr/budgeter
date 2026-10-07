"""The server database: users, sessions and server-wide settings.

Separate from the per-user books (app/books.py), which hold everything a
user actually budgets with. It has its own declarative base and its own
Alembic tree (app/server_migrations, the `[server]` section of alembic.ini).
"""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.pool import StaticPool

from app.config import resolve_data_dir

_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"
_CONNECT_ARGS = {"check_same_thread": False}

_engine: Engine | None = None


class ServerBase(DeclarativeBase):
    pass


def server_db_path() -> Path | None:
    data_dir = resolve_data_dir()
    return data_dir / "server.db" if data_dir is not None else None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        path = server_db_path()
        if path is None:
            from app import server_models  # noqa: F401  (registers the models)

            _engine = create_engine("sqlite://", connect_args=_CONNECT_ARGS, poolclass=StaticPool)
            ServerBase.metadata.create_all(_engine)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            _engine = create_engine(f"sqlite:///{path}", connect_args=_CONNECT_ARGS)
    return _engine


def reset() -> None:
    """Drop the cached engine: the file underneath is about to change (a
    restore), or the settings it was built from have (tests)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None


def SessionLocal() -> Session:
    return Session(bind=get_engine())


def get_server_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def upgrade_to_head() -> None:
    """Bring the server database up to its latest Alembic revision; the
    counterpart of books.upgrade for the server tree. A no-op in in-memory
    test mode, where get_engine creates the tables directly."""
    path = server_db_path()
    if path is None:
        return
    from alembic import command
    from alembic.config import Config

    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = Config(str(_ALEMBIC_INI), ini_section="server")
    cfg.attributes["db_url"] = f"sqlite:///{path}"
    command.upgrade(cfg, "head")

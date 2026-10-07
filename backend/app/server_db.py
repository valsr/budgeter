"""The server database: users, sessions and server-wide settings.

Separate from the per-user books (app/books.py), which hold everything a
user actually budgets with. It has its own declarative base and its own
Alembic tree (app/server_migrations, the `[server]` section of alembic.ini).
"""

import os
import threading
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.pool import NullPool, StaticPool

from app.config import resolve_data_dir

_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"
_CONNECT_ARGS = {"check_same_thread": False}

_engine: Engine | None = None
_lock = threading.RLock()

# Alembic keeps its migration context in process-global state, and requests
# run migrations too (creating or restoring books) -- so every upgrade, in
# either tree, takes this lock. Two at once would cross-wire.
MIGRATION_LOCK = threading.RLock()

# SQLite side files that must not outlive the database they belonged to.
_SIDE_SUFFIXES = ("-wal", "-shm", "-journal")


def remove_side_files(path: Path) -> None:
    for suffix in _SIDE_SUFFIXES:
        Path(str(path) + suffix).unlink(missing_ok=True)


def _enforce_foreign_keys(engine: Engine) -> None:
    """SQLite ignores foreign keys unless asked, per connection. With them
    on, a session can't be created for a user who has just been deleted."""

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class ServerBase(DeclarativeBase):
    pass


def server_db_path() -> Path | None:
    data_dir = resolve_data_dir()
    return data_dir / "server.db" if data_dir is not None else None


def get_engine() -> Engine:
    global _engine
    with _lock:
        if _engine is None:
            path = server_db_path()
            if path is None:
                from app import server_models  # noqa: F401  (registers the models)

                engine = create_engine("sqlite://", connect_args=_CONNECT_ARGS, poolclass=StaticPool)
                _enforce_foreign_keys(engine)
                ServerBase.metadata.create_all(engine)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                # NullPool: every session opens the file afresh, so nothing
                # can go on using a file that a restore has since replaced.
                engine = create_engine(f"sqlite:///{path}", connect_args=_CONNECT_ARGS, poolclass=NullPool)
                _enforce_foreign_keys(engine)
            _engine = engine
        return _engine


def reset() -> None:
    """Drop the cached engine: the file underneath is about to change (a
    restore), or the settings it was built from have (tests)."""
    global _engine
    with _lock:
        if _engine is not None:
            _engine.dispose()
            _engine = None


def replace_database(staged: Path) -> None:
    """Swap an already validated and migrated file in as the server
    database. Holds the engine lock throughout, so no request can build an
    engine on the outgoing file in between."""
    path = server_db_path()
    if path is None:
        raise RuntimeError("The server database has no file in in-memory test mode")
    with _lock:
        reset()
        os.replace(staged, path)
        remove_side_files(path)


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
    upgrade_path(path)


def upgrade_path(path: Path) -> None:
    """Run the server tree's migrations against one specific file."""
    from alembic import command
    from alembic.config import Config

    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = Config(str(_ALEMBIC_INI), ini_section="server")
    cfg.attributes["db_url"] = f"sqlite:///{path}"
    with MIGRATION_LOCK:
        command.upgrade(cfg, "head")

"""Per-user books: one SQLite file per user, all with the same schema.

Everything a user budgets with -- accounts, categories, transactions,
budgets, rules, imports, history -- lives in `<data_dir>/books/<user_id>.db`.
Keeping users in separate files is what isolates them: the services and
their queries never mention a user, because a session can only ever reach
the one file it was opened on (see db.get_db).

The schema is `app.db.Base` and its Alembic tree is app/migrations. The
users themselves live elsewhere, in the server database (app/server_db.py).
"""

import os
import sqlite3
import threading
from collections.abc import Iterable
from pathlib import Path

from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool, StaticPool

from app.config import legacy_database_path, resolve_data_dir
from app.security import hash_token
from app.server_db import MIGRATION_LOCK, remove_side_files
from app.server_models import User

_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"
_CONNECT_ARGS = {"check_same_thread": False}

_engines: dict[int, Engine] = {}
_lock = threading.RLock()


def books_path(user_id: int) -> Path:
    data_dir = resolve_data_dir()
    if data_dir is None:
        raise RuntimeError("Books have no file in in-memory test mode")
    return data_dir / "books" / f"{int(user_id)}.db"


def upgrade(path: Path, revision: str = "head") -> None:
    """Bring one books file up to `revision`, creating it if need be."""
    from alembic import command
    from alembic.config import Config

    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = Config(str(_ALEMBIC_INI))
    cfg.attributes["db_url"] = f"sqlite:///{path}"
    with MIGRATION_LOCK:
        command.upgrade(cfg, revision)


def upgrade_all(user_ids: Iterable[int]) -> None:
    """Startup: migrate every existing books file, so a migration added
    since a file was last touched is applied before anything queries it.
    A user with no file yet is left alone -- one is made on first use."""
    if resolve_data_dir() is None:
        return
    for user_id in user_ids:
        path = books_path(user_id)
        if path.exists():
            upgrade(path)


def _engine_for(user_id: int) -> Engine:
    with _lock:
        engine = _engines.get(user_id)
        if engine is not None and resolve_data_dir() is not None and not books_path(user_id).exists():
            # The file was removed behind the cached engine's back.
            engine.dispose()
            engine = None
        if engine is None:
            if resolve_data_dir() is None:
                from app import models  # noqa: F401  (registers the models)
                from app.db import Base

                engine = create_engine("sqlite://", connect_args=_CONNECT_ARGS, poolclass=StaticPool)
                Base.metadata.create_all(engine)
            else:
                path = books_path(user_id)
                if not path.exists():
                    # Covers a brand-new user and a file deleted outside the
                    # app alike: start from fresh, empty books rather than
                    # failing on "no such table".
                    upgrade(path)
                # NullPool: every session opens the file afresh, so nothing
                # can go on using a file that a restore has since replaced.
                engine = create_engine(f"sqlite:///{path}", connect_args=_CONNECT_ARGS, poolclass=NullPool)
            _engines[user_id] = engine
        return engine


def session_for(user_id: int) -> Session:
    return Session(bind=_engine_for(user_id), autoflush=False)


def ensure_books(user_id: int) -> None:
    """Make sure the user's books exist, creating empty ones if not."""
    _engine_for(user_id)


def create_books(user_id: int) -> None:
    """Fresh, empty books for a newly created user.

    Anything already at that path is removed first: a new account can't
    have legitimate books yet, and a file stranded under a reused id must
    never be handed to whoever gets the id next.
    """
    delete_books(user_id)
    _engine_for(user_id)


def dispose(user_id: int) -> None:
    """Drop the cached engine -- the file underneath is about to be
    replaced or removed, and open handles would keep serving the old one."""
    with _lock:
        engine = _engines.pop(user_id, None)
    if engine is not None:
        engine.dispose()


def dispose_all() -> None:
    with _lock:
        engines = list(_engines.values())
        _engines.clear()
    for engine in engines:
        engine.dispose()


def delete_books(user_id: int) -> None:
    with _lock:
        dispose(user_id)
        if resolve_data_dir() is not None:
            path = books_path(user_id)
            path.unlink(missing_ok=True)
            remove_side_files(path)


def replace_books(user_id: int, staged: Path) -> None:
    """Swap an already validated and migrated file in as a user's books.
    Holds the engine lock throughout, so no request can open the outgoing
    file in between."""
    with _lock:
        dispose(user_id)
        path = books_path(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged, path)
        remove_side_files(path)


def replace_all_books(staged: dict[int, Path]) -> None:
    """Whole-server restore: make the books directory hold exactly the
    staged files -- replacing those, and removing every other user's."""
    with _lock:
        dispose_all()
        books_dir = books_path(0).parent
        books_dir.mkdir(parents=True, exist_ok=True)
        for user_id, path in staged.items():
            replace_books(user_id, path)
        keep = {f"{user_id}.db" for user_id in staged}
        for path in books_dir.glob("*.db"):
            if path.name not in keep:
                path.unlink()
                remove_side_files(path)


# --- the pre-accounts database -----------------------------------------


def _copy_legacy(legacy: Path, dest: Path) -> str | None:
    """Snapshot the legacy file to `dest` and return the API key it held,
    if any. The source is opened read-only: it is never written to.

    Raises sqlite3.Error if the source isn't a budgeter database.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{legacy}?mode=ro", uri=True)
    try:
        # Not a database we recognise -> sqlite3.Error, before dest exists.
        src.execute("SELECT 1 FROM accounts LIMIT 1")
        dst = sqlite3.connect(dest)
        try:
            with dst:
                src.backup(dst)
            try:
                row = dst.execute("SELECT key FROM api_key LIMIT 1").fetchone()
            except sqlite3.OperationalError:
                row = None  # a revision from before (or after) the api_key table
        finally:
            dst.close()
    finally:
        src.close()
    return row[0] if row else None


def claim_legacy_books(sdb: Session, user: User) -> bool:
    """Hand the single-user database from before accounts existed to the
    server's first user, as a copy.

    Returns False -- leaving the caller to create empty books -- unless
    this is the only user, nothing has been claimed before, and
    `BUDGETER_DATABASE_URL` names an existing budgeter database.
    """
    from app.services import users as users_service

    legacy = legacy_database_path()
    if resolve_data_dir() is None or legacy is None or not legacy.is_file():
        return False
    server_settings = users_service.get_settings(sdb)
    if server_settings.legacy_books_claimed:
        return False
    if sdb.execute(select(func.count()).select_from(User)).scalar_one() != 1:
        return False

    dest = books_path(user.id)
    dispose(user.id)
    try:
        legacy_key = _copy_legacy(legacy, dest)
    except sqlite3.Error:
        dest.unlink(missing_ok=True)
        return False
    upgrade(dest)

    if legacy_key:
        # So an MCP adapter already configured with the old shared key keeps working.
        user.api_key_hash = hash_token(legacy_key)
    server_settings.legacy_books_claimed = True
    sdb.commit()
    return True

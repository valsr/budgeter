"""Shared budgets: one SQLite file per shared budget, all with the same schema."""

import os
import threading
from collections.abc import Iterable
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool, StaticPool

from app.config import resolve_data_dir
from app.server_db import CONNECT_ARGS, _enforce_foreign_keys, remove_side_files, run_upgrade

_engines: dict[int, Engine] = {}
_lock = threading.RLock()
_budget_locks: dict[int, threading.Lock] = {}


def shared_path(budget_id: int) -> Path:
    data_dir = resolve_data_dir()
    if data_dir is None:
        raise RuntimeError("Shared budgets have no file in in-memory test mode")
    return data_dir / "shared" / f"{int(budget_id)}.db"


def upgrade(path: Path, revision: str = "head") -> None:
    """Bring one shared budget file up to `revision`, creating it if need be."""
    run_upgrade(path, section="shared", revision=revision)


def upgrade_all(budget_ids: Iterable[int]) -> None:
    """Startup: migrate every shared budget file, creating any that is missing."""
    if resolve_data_dir() is None:
        return
    for budget_id in budget_ids:
        upgrade(shared_path(budget_id))


def _engine_for(budget_id: int) -> Engine:
    with _lock:
        engine = _engines.get(budget_id)
        if engine is not None and resolve_data_dir() is not None and not shared_path(budget_id).exists():
            # The file was removed behind the cached engine's back.
            engine.dispose()
            engine = None
        if engine is None:
            if resolve_data_dir() is None:
                from app import shared_models  # noqa: F401  (registers the models)
                from app.shared_db import SharedBase

                engine = create_engine("sqlite://", connect_args=CONNECT_ARGS, poolclass=StaticPool)
                _enforce_foreign_keys(engine)
                SharedBase.metadata.create_all(engine)
            else:
                path = shared_path(budget_id)
                if not path.exists():
                    upgrade(path)
                # NullPool: every session opens the file afresh, so nothing
                # can go on using a file that a restore has since replaced.
                engine = create_engine(f"sqlite:///{path}", connect_args=CONNECT_ARGS, poolclass=NullPool)
                _enforce_foreign_keys(engine)
            _engines[budget_id] = engine
        return engine


def session_for(budget_id: int) -> Session:
    return Session(bind=_engine_for(budget_id), autoflush=False)


def create(budget_id: int) -> None:
    """A fresh, empty file for a newly created shared budget."""
    delete(budget_id)
    _engine_for(budget_id)


def dispose(budget_id: int) -> None:
    """Drop the cached engine -- the file underneath is about to be replaced or removed."""
    with _lock:
        engine = _engines.pop(budget_id, None)
    if engine is not None:
        engine.dispose()


def dispose_all() -> None:
    with _lock:
        engines = list(_engines.values())
        _engines.clear()
    for engine in engines:
        engine.dispose()


def delete(budget_id: int) -> None:
    with _lock:
        dispose(budget_id)
        if resolve_data_dir() is not None:
            path = shared_path(budget_id)
            path.unlink(missing_ok=True)
            remove_side_files(path)


def replace_all(staged: dict[int, Path]) -> None:
    """Whole-server restore: make the shared directory hold exactly the staged files."""
    with _lock:
        dispose_all()
        shared_dir = shared_path(0).parent
        shared_dir.mkdir(parents=True, exist_ok=True)
        for budget_id, staged_path in staged.items():
            path = shared_path(budget_id)
            os.replace(staged_path, path)
            remove_side_files(path)
        keep = {f"{budget_id}.db" for budget_id in staged}
        for path in shared_dir.glob("*.db"):
            if path.name not in keep:
                path.unlink()
                remove_side_files(path)


def lock_for(budget_id: int) -> threading.Lock:
    """One lock per shared budget, process-wide, for read-modify-write sequences on its file."""
    with _lock:
        return _budget_locks.setdefault(budget_id, threading.Lock())

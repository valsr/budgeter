import os
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.errors import ValidationError

SQLITE_MAGIC = b"SQLite format 3\x00"


@contextmanager
def _temp_db() -> Iterator[Path]:
    """A scratch file path that is removed afterwards."""
    fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        yield Path(tmp_path)
    finally:
        os.unlink(tmp_path)


@contextmanager
def open_image(data: bytes) -> Iterator[sqlite3.Connection]:
    """A connection to a throwaway copy of a database image."""
    with _temp_db() as path:
        path.write_bytes(data)
        conn = sqlite3.connect(path)
        try:
            yield conn
        finally:
            conn.close()


def create_backup_bytes(db_path: str) -> bytes:
    """Snapshot a live SQLite file through its backup API, so a concurrent writer can't tear the copy."""
    with _temp_db() as path:
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(path)
        try:
            with dst:
                src.backup(dst)
        finally:
            src.close()
            dst.close()
        return path.read_bytes()


@contextmanager
def open_db(path: Path, *, readonly: bool = False) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True) if readonly else sqlite3.connect(path)
    try:
        yield conn
    finally:
        conn.close()


def read_revision(conn: sqlite3.Connection) -> str | None:
    """The database's Alembic revision, or None if it has none."""
    try:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    except sqlite3.Error:
        return None
    return row[0] if row else None


def _check_integrity(data: bytes, conn: sqlite3.Connection) -> None:
    try:
        result = conn.execute("PRAGMA integrity_check(1)").fetchone()
    except sqlite3.DatabaseError as e:
        raise ValidationError(f"Uploaded file is not a valid SQLite database: {e}") from e
    if result is None or result[0] != "ok":
        raise ValidationError("Uploaded file failed SQLite integrity check")


def _require_sqlite(data: bytes) -> None:
    if not data.startswith(SQLITE_MAGIC):
        raise ValidationError("Uploaded file is not a valid SQLite database")


def validate_sqlite_bytes(data: bytes) -> None:
    _require_sqlite(data)
    with open_image(data) as conn:
        _check_integrity(data, conn)


def _known_revision(revision: str, section: str | None) -> bool:
    from alembic.script import ScriptDirectory
    from alembic.util import CommandError

    from app.server_db import alembic_config

    try:
        return ScriptDirectory.from_config(alembic_config(section)).get_revision(revision) is not None
    except CommandError:
        return False


def _validate_schema(data: bytes, *, kind: str, required: str, forbidden: str, section: str | None) -> None:
    _require_sqlite(data)
    with open_image(data) as conn:
        _check_integrity(data, conn)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        revision = read_revision(conn)
    if required not in tables or forbidden in tables:
        raise ValidationError(f"Uploaded file is not a budgeter {kind} database")
    if revision is None:
        raise ValidationError(f"Uploaded {kind} database has no schema version")
    if not _known_revision(revision, section):
        # Typically a backup from a newer version of the app: no migration path from it.
        raise ValidationError(
            f"Uploaded {kind} database is at schema version {revision}, which this version of the app doesn't know"
        )


def validate_books_bytes(data: bytes) -> None:
    """One user's books, at a revision this build can migrate from."""
    _validate_schema(data, kind="books", required="accounts", forbidden="users", section=None)


def validate_server_bytes(data: bytes) -> None:
    _validate_schema(data, kind="server", required="users", forbidden="accounts", section="server")


def _verify_schema(path: Path, metadata, kind: str) -> None:
    """After migrating: every table and column the app's models expect must actually be there."""
    with open_db(path) as conn:
        for table in metadata.sorted_tables:
            columns = {row[1] for row in conn.execute(f'PRAGMA table_info("{table.name}")')}
            if {column.name for column in table.columns} - columns:
                raise ValidationError(
                    f"Uploaded {kind} database doesn't have the expected structure (table {table.name!r})"
                )


def _stage(data: bytes, staged: Path, *, kind: str, validate, upgrade, metadata) -> Path:
    """Write an uploaded image to `staged` as a ready-to-swap file: validated, migrated to head and
    checked against the models. Raises ValidationError, leaving nothing behind."""
    validate(data)
    staged.parent.mkdir(parents=True, exist_ok=True)
    try:
        staged.write_bytes(data)
        try:
            upgrade(staged)
        except Exception as e:  # noqa: BLE001 -- whatever a migration trips on
            raise ValidationError(f"Uploaded {kind} database couldn't be brought up to date: {e}") from e
        _verify_schema(staged, metadata, kind)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    return staged


def stage_books(data: bytes, staged: Path) -> Path:
    from app import books
    from app import models  # noqa: F401  (registers the models)
    from app.db import Base

    return _stage(
        data, staged, kind="books", validate=validate_books_bytes, upgrade=books.upgrade, metadata=Base.metadata
    )


def stage_server(data: bytes, staged: Path) -> Path:
    from app import server_db, server_models  # noqa: F401

    return _stage(
        data,
        staged,
        kind="server",
        validate=validate_server_bytes,
        upgrade=server_db.upgrade_path,
        metadata=server_db.ServerBase.metadata,
    )

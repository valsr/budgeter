import os
import sqlite3
import tempfile
from pathlib import Path

from app.errors import ValidationError

SQLITE_MAGIC = b"SQLite format 3\x00"


def resolve_sqlite_path(database_url: str) -> str:
    """Extract the filesystem path from a `sqlite:///...` URL.

    `sqlite:///relative/path.db` -> `relative/path.db` (3 slashes = relative)
    `sqlite:////abs/path.db` -> `/abs/path.db` (4 slashes = absolute)
    """
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValidationError("Backup/restore requires a SQLite database_url")
    return database_url[len(prefix):]


def create_backup_bytes(db_path: str) -> bytes:
    """Snapshot the live SQLite file via sqlite3's backup API (rather than
    reading the file's raw bytes directly) so a concurrent writer or an
    open WAL file can't produce a torn/inconsistent copy.
    """
    fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(tmp_path)
        try:
            with dst:
                src.backup(dst)
        finally:
            src.close()
            dst.close()
        return Path(tmp_path).read_bytes()
    finally:
        os.unlink(tmp_path)


def validate_sqlite_bytes(data: bytes) -> None:
    if not data.startswith(SQLITE_MAGIC):
        raise ValidationError("Uploaded file is not a valid SQLite database")

    fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        Path(tmp_path).write_bytes(data)
        conn = sqlite3.connect(tmp_path)
        try:
            result = conn.execute("PRAGMA integrity_check(1)").fetchone()
        except sqlite3.DatabaseError as e:
            raise ValidationError(f"Uploaded file is not a valid SQLite database: {e}") from e
        finally:
            conn.close()
        if result is None or result[0] != "ok":
            raise ValidationError("Uploaded file failed SQLite integrity check")
    finally:
        os.unlink(tmp_path)


def write_backup_bytes(db_path: str, data: bytes) -> None:
    """Validate then atomically replace the live database file.

    Writes to a temp file in the same directory first and uses os.replace
    (atomic on the same filesystem) so a crash mid-write can't leave a
    half-written database in place.
    """
    validate_sqlite_bytes(data)

    directory = os.path.dirname(os.path.abspath(db_path)) or "."
    fd, tmp_path = tempfile.mkstemp(suffix=".db", dir=directory)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp_path, db_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

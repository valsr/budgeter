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


def _inspect_sqlite_bytes(data: bytes) -> tuple[set[str], str | None]:
    """(table names, Alembic revision or None) of a validated SQLite image."""
    fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        Path(tmp_path).write_bytes(data)
        conn = sqlite3.connect(tmp_path)
        try:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            revision = None
            if "alembic_version" in tables:
                row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
                revision = row[0] if row else None
        finally:
            conn.close()
        return tables, revision
    finally:
        os.unlink(tmp_path)


def _known_revision(revision: str, ini_section: str) -> bool:
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from alembic.util import CommandError

    ini = Path(__file__).resolve().parent.parent.parent / "alembic.ini"
    script = ScriptDirectory.from_config(Config(str(ini), ini_section=ini_section))
    try:
        return script.get_revision(revision) is not None
    except CommandError:
        return False


def _validate_schema(data: bytes, *, kind: str, required: str, forbidden: str, ini_section: str) -> None:
    validate_sqlite_bytes(data)
    tables, revision = _inspect_sqlite_bytes(data)
    if required not in tables or forbidden in tables:
        raise ValidationError(f"Uploaded file is not a budgeter {kind} database")
    if revision is None:
        raise ValidationError(f"Uploaded {kind} database has no schema version")
    if not _known_revision(revision, ini_section):
        # Typically a backup taken from a newer version of the app: there is
        # no migration path from a revision this build has never heard of.
        raise ValidationError(
            f"Uploaded {kind} database is at schema version {revision}, which this version of the app doesn't know"
        )


def validate_books_bytes(data: bytes) -> None:
    """A SQLite image that is one user's books, at a revision this build
    can migrate from -- not a server database, not some other app's file."""
    _validate_schema(data, kind="books", required="accounts", forbidden="users", ini_section="alembic")


def validate_server_bytes(data: bytes) -> None:
    _validate_schema(data, kind="server", required="users", forbidden="accounts", ini_section="server")

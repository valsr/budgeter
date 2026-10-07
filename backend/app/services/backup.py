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


def _verify_schema(path: Path, metadata, kind: str) -> None:
    """After migrating: every table and column the app's models expect must
    actually be there. A file can carry a plausible revision stamp and still
    be nothing like the schema that stamp promises."""
    conn = sqlite3.connect(path)
    try:
        for table in metadata.sorted_tables:
            columns = {row[1] for row in conn.execute(f'PRAGMA table_info("{table.name}")')}
            missing = {column.name for column in table.columns} - columns
            if missing:
                raise ValidationError(
                    f"Uploaded {kind} database doesn't have the expected structure (table {table.name!r})"
                )
    finally:
        conn.close()


def stage_books(data: bytes, directory: Path, name: str | None = None) -> Path:
    """Turn an uploaded books image into a ready-to-swap file in `directory`:
    validated, migrated to head, and checked against the models.

    Everything that can go wrong goes wrong here, on a copy -- the caller's
    live books are untouched until it os.replace()s the returned path in.
    Raises ValidationError and leaves nothing behind on any failure.
    """
    from app import books
    from app import models  # noqa: F401  (registers the models)
    from app.db import Base

    validate_books_bytes(data)
    directory.mkdir(parents=True, exist_ok=True)
    if name is None:
        fd, tmp = tempfile.mkstemp(suffix=".restore", dir=directory)
        os.close(fd)
        staged = Path(tmp)
    else:
        staged = directory / name
    try:
        staged.write_bytes(data)
        try:
            books.upgrade(staged)
        except Exception as e:  # noqa: BLE001 -- whatever a migration trips on
            raise ValidationError(f"Uploaded books database couldn't be brought up to date: {e}") from e
        _verify_schema(staged, Base.metadata, "books")
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    return staged


def stage_server(data: bytes, staged: Path) -> Path:
    """The server-database counterpart of stage_books."""
    from app import server_db, server_models  # noqa: F401

    validate_server_bytes(data)
    try:
        staged.write_bytes(data)
        try:
            server_db.upgrade_path(staged)
        except Exception as e:  # noqa: BLE001
            raise ValidationError(f"Uploaded server database couldn't be brought up to date: {e}") from e
        _verify_schema(staged, server_db.ServerBase.metadata, "server")
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    return staged

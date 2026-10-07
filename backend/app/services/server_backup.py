"""Whole-server backup: the server database plus every user's books, as
one zip. Restoring it replaces everything on the server."""

import datetime as dt
import io
import re
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from app import books, server_db
from app.config import resolve_data_dir
from app.errors import ValidationError
from app.services import backup as backup_service
from app.services import users as users_service

_SERVER_MEMBER = "server.db"
_BOOKS_MEMBER = re.compile(r"books/([1-9][0-9]*)\.db")


def _data_dir() -> Path:
    data_dir = resolve_data_dir()
    if data_dir is None:
        raise ValidationError("Whole-server backup needs a data directory on disk")
    return data_dir


def archive_filename() -> str:
    return f"budgeter-server-backup-{dt.date.today().isoformat()}.zip"


def create_archive() -> bytes:
    data_dir = _data_dir()
    with server_db.SessionLocal() as sdb:
        user_ids = [user.id for user in users_service.list_users(sdb)]

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(_SERVER_MEMBER, backup_service.create_backup_bytes(str(data_dir / "server.db")))
        for user_id in user_ids:
            path = books.books_path(user_id)
            if path.exists():
                archive.writestr(f"books/{user_id}.db", backup_service.create_backup_bytes(str(path)))
    return out.getvalue()


def _read_members(data: bytes) -> tuple[bytes, dict[int, bytes]]:
    """Validate an uploaded archive in full and return (server image,
    {user_id: books image}). Nothing is written to the data directory."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise ValidationError("Uploaded file is not a zip archive") from e

    with archive:
        names = archive.namelist()
        if len(set(names)) != len(names):
            raise ValidationError("Archive lists the same file twice")
        # Names are matched whole against the two shapes this app writes -- never joined onto a path
        # -- so "..", absolute paths and stray files are all refused here.
        unexpected = [n for n in names if n != _SERVER_MEMBER and not _BOOKS_MEMBER.fullmatch(n)]
        if unexpected:
            raise ValidationError(f"Archive contains an unexpected file: {unexpected[0]!r}")
        if _SERVER_MEMBER not in names:
            raise ValidationError("Archive has no server.db")

        try:
            server_bytes = archive.read(_SERVER_MEMBER)
            books_bytes = {
                int(_BOOKS_MEMBER.fullmatch(n).group(1)): archive.read(n) for n in names if n != _SERVER_MEMBER
            }
        except (zipfile.BadZipFile, OSError, RuntimeError) as e:
            raise ValidationError(f"Archive is damaged: {e}") from e

    backup_service.validate_server_bytes(server_bytes)
    for user_id, image in books_bytes.items():
        try:
            backup_service.validate_books_bytes(image)
        except ValidationError as e:
            raise ValidationError(f"books/{user_id}.db: {e}") from e

    # Books with no account behind them would sit on disk until some future
    # user was given that id -- and with it, somebody else's data.
    orphans = sorted(set(books_bytes) - _user_ids_in(server_bytes))
    if orphans:
        raise ValidationError(f"Archive has books for a user that isn't in its server.db: books/{orphans[0]}.db")
    return server_bytes, books_bytes


def _user_ids_in(server_bytes: bytes) -> set[int]:
    with backup_service.open_image(server_bytes) as conn:
        return {row[0] for row in conn.execute("SELECT id FROM users")}


def _require_active_admin(server_file: Path) -> None:
    """Refuse a server database that would lock everyone out of administration: it has users, but
    none who is an enabled admin."""
    conn = sqlite3.connect(server_file)
    try:
        users, active_admins = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(is_admin AND NOT is_disabled), 0) FROM users"
        ).fetchone()
    finally:
        conn.close()
    if users and not active_admins:
        raise ValidationError("Archive's server.db has no active admin: nobody could manage the server after restoring it")


def restore_archive(data: bytes) -> None:
    """Replace the server database and all books with the archive's."""
    data_dir = _data_dir()
    server_bytes, books_bytes = _read_members(data)

    # Staged on the same filesystem so each os.replace is atomic.
    staging = Path(tempfile.mkdtemp(prefix=".restore-", dir=data_dir))
    try:
        staged_server = backup_service.stage_server(server_bytes, staging / "server.db")
        _require_active_admin(staged_server)
        staged_books: dict[int, Path] = {}
        for user_id, image in books_bytes.items():
            try:
                staged_books[user_id] = backup_service.stage_books(image, staging, name=f"{user_id}.db")
            except ValidationError as e:
                raise ValidationError(f"books/{user_id}.db: {e}") from e

        server_db.replace_database(staged_server)
        books.replace_all_books(staged_books)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

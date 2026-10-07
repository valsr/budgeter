"""The detailed health report for admins (GET /api/admin/health)."""

import platform
import sqlite3

from sqlalchemy.orm import Session

from app import books, runtime, server_db
from app.config import resolve_data_dir
from app.errors import ValidationError
from app.routers.health import uptime_seconds
from app.services import server_config
from app.services import users as users_service
from app.version import get_version


def _revision(connection) -> str | None:
    try:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    except sqlite3.Error:
        return None
    return row[0] if row else None


def _books_report(user_ids: list[int]) -> tuple[dict, str, str | None]:
    """(storage figures, books check, a books schema revision)."""
    files = size = broken = 0
    revision = None
    for user_id in user_ids:
        path = books.books_path(user_id)
        if not path.exists():
            continue  # created on first use; not a fault
        files += 1
        size += path.stat().st_size
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                conn.execute("SELECT 1 FROM accounts LIMIT 1")
                revision = _revision(conn) or revision
            finally:
                conn.close()
        except sqlite3.Error:
            broken += 1
    check = "ok" if broken == 0 else f"{broken} of {files} books files can't be read"
    return {"books_files": files, "books_bytes": size}, check, revision


def report(sdb: Session) -> dict:
    all_users = users_service.list_users(sdb)
    server_settings = users_service.get_settings(sdb)
    data_dir = resolve_data_dir()

    checks = {"server_db": "ok", "books": "ok", "ssl": "disabled"}
    storage = schema = None
    if data_dir is not None:
        storage, checks["books"], books_revision = _books_report([u.id for u in all_users])
        server_path = server_db.server_db_path()
        storage["server_db_bytes"] = server_path.stat().st_size
        conn = sqlite3.connect(f"file:{server_path}?mode=ro", uri=True)
        try:
            schema = {"server": _revision(conn), "books": books_revision}
        finally:
            conn.close()

    # Checked against what is *saved*, so a certificate that has been moved or has stopped matching
    # its key shows up here -- before the restart that would refuse to start because of it.
    if server_settings.ssl_enabled:
        try:
            server_config.check_ssl_files(server_settings.ssl_certfile, server_settings.ssl_keyfile)
            checks["ssl"] = "ok"
        except ValidationError as e:
            checks["ssl"] = str(e)

    healthy = all(value in ("ok", "disabled") for value in checks.values())
    serving = runtime.current
    return {
        "status": "ok" if healthy else "degraded",
        "version": get_version().as_dict(),
        "checks": checks,
        "started_at": runtime.STARTED_AT,
        "uptime_seconds": uptime_seconds(),
        "serving": {"port": serving.port, "https": serving.ssl_enabled} if serving else None,
        "restart_required": server_config.restart_required(server_settings),
        "users": {
            "total": len(all_users),
            "active_admins": sum(1 for u in all_users if u.is_admin and not u.is_disabled),
            "disabled": sum(1 for u in all_users if u.is_disabled),
        },
        "data_dir": str(data_dir) if data_dir is not None else None,
        "storage": storage,
        "schema": schema,
        "python_version": platform.python_version(),
    }

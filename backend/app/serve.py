"""Start the server the way Settings → Server says to."""

import sys
import tempfile

import uvicorn

from app import runtime, server_db
from app.config import resolve_data_dir, settings
from app.services import server_config


def _prepare_data_dir() -> None:
    """Say where the data lives, and stop now if it can't be written."""
    data_dir = resolve_data_dir()
    if data_dir is None:
        return
    print(f"budgeter: data directory: {data_dir}", file=sys.stderr)
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=data_dir, prefix=".write-check-"):
            pass
    except OSError as e:
        print(
            f"budgeter: not starting -- can't write to the data directory {data_dir}: {e}\n"
            "Everything the app stores (server.db, books/) goes there. If it is a mounted\n"
            "directory, make it writable by the user the server runs as (uid 1000 in the\n"
            "container), or point BUDGETER_DATA_DIR somewhere else.",
            file=sys.stderr,
        )
        raise SystemExit(1) from e


def main() -> None:
    _prepare_data_dir()
    # The settings live in the server database, so it has to be current
    # before they can be read -- ahead of the app's own startup hook.
    server_db.upgrade_to_head()
    try:
        with server_db.SessionLocal() as db:
            plan = server_config.resolve_startup(db)
    except server_config.StartupError as e:
        print(
            f"budgeter: not starting -- SSL is enabled in Settings → Server, but: {e}\n"
            "Put the certificate and key back in place, or start once with\n"
            "BUDGETER_SSL_DISABLED=true to serve plain HTTP and fix the settings.",
            file=sys.stderr,
        )
        raise SystemExit(1) from e

    from app.main import app

    runtime.current = plan
    options: dict = {"host": settings.host, "port": plan.port}
    if plan.ssl_enabled:
        options["ssl_certfile"] = plan.ssl_certfile
        options["ssl_keyfile"] = plan.ssl_keyfile
    uvicorn.run(app, **options)


if __name__ == "__main__":
    main()

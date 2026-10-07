"""Start the server the way Settings → Server says to.

    python -m app.serve

Reads the port and SSL settings from the server database and runs uvicorn
with them. This is how the container starts the app. `uvicorn app.main:app`
still works (handy with --reload in development) but ignores those settings:
the port and TLS are then whatever that command line says.
"""

import sys

import uvicorn

from app import runtime, server_db
from app.config import settings
from app.services import server_config


def main() -> None:
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

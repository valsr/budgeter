#!/bin/sh
set -e

# Schema migrations run inside the app itself on startup (see main.py's
# lifespan hook: server_db.upgrade_to_head(), then books.upgrade_all()) —
# don't also run `alembic upgrade head` here as a separate process. Doing
# both back-to-back against the same SQLite file was observed to deadlock
# on this volume's locking behavior.
#
# app.serve reads the port and SSL settings saved in Settings → Server and
# starts uvicorn with them; with SSL enabled it exits non-zero if the
# certificate or key can't be found. The bind address is BUDGETER_HOST
# (0.0.0.0 in the image).
exec python -m app.serve

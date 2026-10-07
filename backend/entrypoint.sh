#!/bin/sh
set -e

# Schema migrations run inside the app itself on startup (see main.py's
# lifespan hook: server_db.upgrade_to_head(), then books.upgrade_all()) —
# don't also run `alembic upgrade head` here as a separate process. Doing
# both back-to-back against the same SQLite file was observed to deadlock
# on this volume's locking behavior.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000

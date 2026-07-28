#!/bin/sh
set -e

# Schema migrations run inside the app itself on startup (see
# upgrade_to_head() in app/db.py, called from main.py's lifespan hook) —
# don't also run `alembic upgrade head` here as a separate process. Doing
# both back-to-back against the same SQLite file was observed to deadlock
# on this volume's locking behavior.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000

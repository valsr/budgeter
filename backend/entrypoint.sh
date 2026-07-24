#!/bin/sh
set -e

# BUDGETER_DATABASE_URL defaults to a file under /data (see Containerfile),
# which is where the named volume is mounted — migrations must run against
# that same path before the server starts.
alembic upgrade head

exec uvicorn app.main:app --host 0.0.0.0 --port 8000

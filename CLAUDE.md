# CLAUDE.md

Project-specific guidance for Claude Code when working in this repository.

## Database schema changes

The database is versioned with Alembic (`backend/app/migrations/`). The app
auto-upgrades to the latest revision on startup — `upgrade_to_head()` in
`backend/app/db.py`, called from `main.py`'s lifespan hook — so a running
server always self-heals a stale or missing schema. That self-healing only
works if a migration exists for every schema change, so:

**Any change to a SQLAlchemy model (`backend/app/models/`) must ship with a
matching Alembic migration in the same change.** Generate one from
`backend/`:

```bash
.venv/bin/alembic revision --autogenerate -m "short description"
```

Then read the generated file before committing — autogenerate doesn't
reliably catch everything (enum value changes, some constraint changes,
column renames look like drop+add). Never edit a migration that's already
been committed; add a new one on top instead.

The bare in-memory `sqlite://` URL (what `backend/tests/conftest.py` sets by
default) is a sentinel that skips auto-migration — the test suite creates
tables directly via `Base.metadata.create_all`, since each test run gets a
fresh in-memory DB anyway.

## Local dev database

`backend/budgeter.db` is the live SQLite file both the dev `uvicorn --reload`
server and any local scratch/manual testing use. It is **not** the same
database pytest uses (pytest is fully in-memory, see above) — don't assume
running the test suite is a safe, isolated operation with respect to that
file. In particular, never `rm`/reset `backend/budgeter.db` as part of a test
workflow; if you need a clean DB for a one-off manual check, point
`BUDGETER_DATABASE_URL` at a scratch path instead.

# CLAUDE.md

Project-specific guidance for Claude Code when working in this repository.

## Database schema changes

There are two schemas, each with its own declarative base and its own
Alembic tree:

| Schema | Models | Base | Migrations | Lives in |
|---|---|---|---|---|
| **Books** — one user's accounts, categories, transactions, budgets, rules, imports, history | `backend/app/models/` | `app.db.Base` | `backend/app/migrations/` | `books/<user_id>.db`, one file per user |
| **Server** — users, sessions, server settings | `backend/app/server_models/` | `app.server_db.ServerBase` | `backend/app/server_migrations/` | `server.db` |

The app auto-upgrades both on startup (`main.py`'s lifespan hook calls
`server_db.upgrade_to_head()`, then `books.upgrade_all()` for every user's
file), and a books file is also migrated when it is created or restored — so
a running server always self-heals a stale or missing schema. That
self-healing only works if a migration exists for every schema change, so:

**Any change to a SQLAlchemy model must ship with a matching Alembic
migration in the same change, in the tree that matches the model's schema.**
Generate one from `backend/`:

```bash
# Books (app/models): autogenerate diffs against a database at head, so
# point it at a scratch file — never at a real user's books.
export BUDGETER_DATABASE_URL=sqlite:///$(mktemp -d)/scratch.db
.venv/bin/alembic upgrade head
.venv/bin/alembic revision --autogenerate -m "short description"

# Server (app/server_models): the second tree, selected with --name.
BUDGETER_DATA_DIR=$(mktemp -d) .venv/bin/alembic --name server upgrade head   # same dir for both commands
BUDGETER_DATA_DIR=<that dir> .venv/bin/alembic --name server revision --autogenerate -m "short description"
```

A table belongs in the server schema only if it is about who can log in or
about the server as a whole. Anything a user budgets with goes in books:
keeping each user's data in their own file is what isolates users from each
other, which is why no books table (or query) carries a user id.

Then read the generated file before committing — autogenerate doesn't
reliably catch everything (enum value changes, some constraint changes,
column renames look like drop+add). Never edit a migration that's already
been committed; add a new one on top instead.

The bare in-memory `sqlite://` URL (what `backend/tests/conftest.py` sets by
default) is a sentinel that skips auto-migration for both schemas — the test
suite creates tables directly via `create_all`, since each test gets fresh
in-memory databases anyway. Tests that are about the files themselves (the
`files` / `make_client` fixtures) run file-backed under pytest's `tmp_path`.

## Local dev data

The dev `uvicorn --reload` server keeps its live data in `backend/`:
`server.db` (logins) and `books/<user_id>.db` (each user's books). The data
directory is `BUDGETER_DATA_DIR`, defaulting to the directory of the file
`BUDGETER_DATABASE_URL` names.

`backend/budgeter.db` is the database from before user accounts existed. The
app only ever **reads** it: the first user to register on a server gets a
copy of it as their books (`books.claim_legacy_books`). It is the untouched
fallback for that migration, so it still must not be modified or removed.

None of these are what pytest uses (pytest is in-memory or under `tmp_path`,
see above) — but don't assume running things by hand is isolated from them.
Never `rm`/reset `backend/budgeter.db`, `backend/server.db` or
`backend/books/` as part of a test workflow; for a one-off manual check,
point `BUDGETER_DATABASE_URL` (and so the data directory) at a scratch path
instead, copying `budgeter.db` there first if you want real data.

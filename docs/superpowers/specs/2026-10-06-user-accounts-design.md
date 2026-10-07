# User accounts and per-user books — design

Date: 2026-10-06
Status: awaiting review

## Goal

Budgeter is single-user today: one SQLite file, one shared API key, no login.
This change lets several people use one server, each with their own separate
books, behind a username/password login. Every account is an admin by
default; admins manage users and server settings.

Success means:

- Two users on one server never see or affect each other's accounts,
  categories, transactions, budgets, rules, imports or history.
- The existing data survives and becomes the first registered user's books.
- The MCP adapter keeps working once it is given a user's API key.
- Existing services, queries and their tests are not rewritten.

## Decisions already made

| Topic         | Decision                                                                     |
| ------------- | ---------------------------------------------------------------------------- |
| Tenancy       | Separate books per user                                                      |
| Isolation     | One SQLite file per user, plus a server database                             |
| API keys      | One per user, stored hashed, shown once on regeneration                      |
| Admin powers  | Disable/enable, reset password, delete user and data, grant/revoke admin     |
| Backup        | Per-user backup/restore of own books, plus admin whole-server backup/restore |
| Existing data | Copied to the first user who registers                                       |
| Registration  | Server setting, default open; always open while there are no users           |

## Out of scope

- Sharing one set of books between users (the storage layout allows it later).
- Login rate limiting, password reset by email, two-factor authentication.
- Roles beyond the single admin flag.
- Databases other than SQLite.

## Storage

### Layout

All files live in one data directory: `BUDGETER_DATA_DIR`, defaulting to the
directory that holds the file named by `BUDGETER_DATABASE_URL` (`backend/` in
dev, `/data` in the container).

```
<data_dir>/
  server.db            users, sessions, server_settings
  books/<user_id>.db   one user's books: every table that exists today
  budgeter.db          the pre-accounts database, left in place (see below)
```

### Two schemas

- **Books schema** — the existing `Base` and every existing model, unchanged
  except that the `api_key` table is dropped (keys move to the server
  database). Its Alembic tree stays at `backend/app/migrations/`.
- **Server schema** — a new `ServerBase` with the models below, in
  `backend/app/server_models/`, with its own Alembic tree at
  `backend/app/server_migrations/` (a second named section in `alembic.ini`).

Server tables:

- `users`: `id`, `username` (stored lower-case, unique), `password_hash`,
  `is_admin` (default true), `is_disabled` (default false), `api_key_hash`
  (nullable, unique), `created_at`.
- `sessions`: `id`, `user_id`, `token_hash` (unique), `created_at`,
  `expires_at`.
- `server_settings`: single row; `registration_open` (default true),
  `legacy_books_claimed` (default false).

### Engines and sessions

A new module `backend/app/books.py` owns per-user engines:

- `books_path(user_id)` returns the user's file path.
- `session_for(user_id)` returns a session bound to that user's engine.
  Engines are created on first use and cached by user id.
- `dispose(user_id)` drops the cached engine (before restore or delete).
- `create_books(user_id)` creates the file and migrates it to head.

`get_db` becomes a dependency on the current user and yields
`books.session_for(user.id)`. Every existing router and service keeps taking
a plain `Session` and needs no change. A separate `get_server_db` yields a
server-database session for auth and admin code.

Two places open their own session today and must be given the user id:

- `services/categorization.py` (background task) takes a `user_id` argument.
- `main.py`'s startup purge of expired history loops over all users.

### Migrations

`upgrade_to_head()` upgrades the server database, then every books file found
for an existing user. The in-memory `sqlite://` test sentinel still skips
Alembic and uses `create_all` for both schemas.

The books Alembic `env.py` takes its target URL from a `-x db=<path>` argument
when given, falling back to `BUDGETER_DATABASE_URL`, so
`alembic revision --autogenerate` keeps working against a scratch books file.
`CLAUDE.md` is updated to describe both trees, and to say which one a model
change belongs to.

### Existing data

On the first successful registration, if `server_settings.legacy_books_claimed`
is false and the legacy file exists, it is **copied** (through SQLite's backup
API) to `books/<user_id>.db` and migrated to head; the flag is then set. If
the legacy `api_key` table holds a key, its hash becomes that user's
`api_key_hash`, so an already-configured MCP adapter keeps working.

The legacy file is never modified or deleted. It can be removed by hand once
the migration is confirmed.

Any later user, or a first user with no legacy file, gets empty books.

## Authentication

### Passwords

Hashed with `hashlib.scrypt` and a per-user random salt, stored as
`scrypt$<n>$<r>$<p>$<salt>$<hash>`; verified with `hmac.compare_digest`. No
new dependency.

Rules: username 3–32 characters from `a-z 0-9 _ . -`, compared
case-insensitively; password at least 8 characters.

### Sessions

Login generates a 32-byte random token. Its SHA-256 hash is stored in
`sessions`; the token itself goes to the browser in a cookie named
`budgeter_session` — httpOnly, SameSite=Lax, `Secure` when the request came
over HTTPS. Sessions last 30 days and the expiry slides forward when a request
arrives with less than 29 days left. Expired sessions are purged at startup.

### Resolving the current user

`auth.current_user` replaces `require_api_key`:

1. An `Authorization: Bearer <key>` header is hashed and matched against
   `users.api_key_hash`.
2. Otherwise the session cookie is hashed and matched against `sessions`.
3. No match, an expired session, or a disabled user gives 401.

`auth.require_admin` builds on it and gives 403 to non-admins.

Cross-site request forgery is covered by SameSite=Lax plus the existing
single-origin CORS allow-list. The frontend sends `credentials: "include"`.

### API keys

`POST /api/settings/api-key/regenerate` returns the new key once and stores
only its hash. `GET /api/settings/api-key` now returns whether a key exists,
not the key. The `BUDGETER_API_KEY` environment default no longer grants
access.

## API

All under `/api`. Unless marked, an endpoint requires a logged-in user.

Auth (`routers/auth.py`):

| Method | Path             | Notes                                                                         |
| ------ | ---------------- | ----------------------------------------------------------------------------- |
| GET    | `/auth/status`   | Public. `{registration_open, has_users}`                                      |
| POST   | `/auth/register` | Public. 403 when registration is closed and users exist. Logs the new user in |
| POST   | `/auth/login`    | Public. Same 401 for unknown user, wrong password, disabled                   |
| POST   | `/auth/logout`   | Deletes the session                                                           |
| GET    | `/auth/me`       | `{id, username, is_admin}`                                                    |
| POST   | `/auth/password` | Needs the current password. Ends the user's other sessions                    |
| DELETE | `/auth/me`       | Needs the current password. Deletes the user and their books                  |

Admin (`routers/admin.py`, all admin-only):

| Method      | Path                    | Notes                                           |
| ----------- | ----------------------- | ----------------------------------------------- |
| GET         | `/admin/users`          | id, username, is_admin, is_disabled, created_at |
| POST        | `/admin/users`          | Create a user with an initial password          |
| PATCH       | `/admin/users/{id}`     | Any of `is_admin`, `is_disabled`, `password`    |
| DELETE      | `/admin/users/{id}`     | Deletes the user, sessions and books file       |
| GET / PATCH | `/admin/settings`       | `registration_open`                             |
| GET         | `/admin/backup`         | Whole-server zip                                |
| POST        | `/admin/backup/restore` | Replaces everything                             |

Guards, enforced in a `services/users.py` layer and returned as 409:

- The last active admin cannot be demoted, disabled or deleted — by an admin
  or by themselves.
- Disabling a user deletes their sessions; their API key stops working
  because `current_user` rejects disabled users.

Admins have no endpoint that reads another user's books.

## Backup and restore

**Per user** — the existing `/api/backup` endpoints, now acting on the
caller's own books file. Restore validates the upload as today, additionally
requires an `alembic_version` table from the books tree, disposes the user's
engine, swaps the file atomically, and migrates it to head.

**Whole server** — `GET /api/admin/backup` returns a zip holding `server.db`
and every `books/<id>.db`, each snapshotted through SQLite's backup API.
Restore validates every member before touching anything, disposes all
engines, replaces the files, removes books files not in the archive, and
migrates everything to head. Sessions come from the archive, so users
(including the admin who ran it) may need to log in again; the UI says so
before confirming.

## Frontend

- `AuthProvider` (new, wraps the app) calls `/auth/me` on load. While it is
  pending the app shows nothing; on 401 it shows the auth screen.
- `pages/Login.tsx`: username and password, with a switch to a register form.
  The register option appears only when `/auth/status` reports registration
  open or no users. With no users the screen says the first account will take
  over the existing data.
- `api/client.ts`: sends credentials, drops the stored API key and the
  `Authorization` header, and reports any 401 to `AuthProvider`, which returns
  to the auth screen.
- Sidebar: the brand subtitle shows the username in place of
  "local · single user", with a log-out control.
- Settings tabs:
  - **Account** (replaces the API key tab): change password, API key status
    and regenerate-and-show-once, delete my account.
  - **Backup & restore**: unchanged in appearance, now scoped to my books.
  - **Users** (admin): table with enable/disable, admin toggle, reset
    password, delete; a create-user form.
  - **Server** (admin): registration toggle, whole-server backup and restore.
  - Categories, Rules and History retention are unchanged.
- The remembered Overview budget and Categories selection keys gain the user
  id, so two users sharing a browser do not overwrite each other.

## Error handling

- Login failures return one generic message, whatever the cause.
- Register returns 409 for a taken username and 422 for rule violations, with
  a message naming the rule.
- A user whose books file is missing (deleted outside the app) gets fresh
  empty books on next access, rather than a 500.
- A failed whole-server restore leaves the existing files in place: all
  members are validated and staged in the data directory before any swap.

## Testing

Backend (pytest, in-memory):

- Password hashing round-trip and rejection of a wrong password.
- Register, login, logout, session expiry and sliding renewal.
- Registration gating: open, closed, and always open with no users.
- API key: regenerate shows once, the key authenticates, the old key stops.
- Disabled user: login refused, session and key rejected.
- Last-admin guards for demote, disable, delete and self-delete.
- Isolation: two users, each creates data, neither can list or fetch the
  other's by id.
- Legacy claim: first user receives the legacy data and key; second does not;
  the legacy file is unchanged.
- Per-user backup round-trip; whole-server backup round-trip; a restore with
  an invalid member changes nothing.
- Both migration trees upgrade from empty to head.

`conftest.py` keeps the `client`, `db_session` and `auth_headers` fixtures:
a fixture user is created holding the `test-api-key` hash, and `get_db` is
overridden as today, so the existing router tests run unchanged.

Frontend (vitest): the auth gate (pending, logged out, logged in), login and
register forms, the 401 redirect, the Account, Users and Server tabs, and
admin-only tab visibility.

## Documentation

Update `docs/requirements.md` (users, auth, and the out-of-scope list),
`docs/container.md` (data directory layout and backup), `README.md`,
`mcp_adapter/README.md` (where the key comes from), and `CLAUDE.md` (two
migration trees; the dev database is now `backend/books/<id>.db`).

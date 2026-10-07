# User Accounts and Per-User Books Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let several people share one Budgeter server, each with separate books behind a username/password login, with admins managing users and server settings.

**Architecture:** A new server database (`server.db`) holds users, sessions and server settings. Each user's books are their own SQLite file (`books/<user_id>.db`) using today's schema, so `get_db` simply yields a session on the caller's file and existing services stay untouched. Auth resolves a user from a bearer API key or a session cookie.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic (two trees), SQLite, stdlib `hashlib.scrypt`; React 19, react-router 7, vitest.

**Spec:** `docs/superpowers/specs/2026-10-06-user-accounts-design.md`

## Global Constraints

- No new Python or npm dependencies.
- Username: 3–32 characters from `a-z 0-9 _ . -`, trimmed and lower-cased before validation and storage.
- Password: 8–256 characters. Hash format `scrypt$<n>$<r>$<p>$<salt>$<hash>` with n=16384, r=8, p=1, 16-byte salt, hex-encoded.
- Session cookie: name `budgeter_session`, httpOnly, SameSite=Lax, path `/`, `Secure` only when `request.url.scheme == "https"`, lifetime 30 days, renewed when less than 29 days remain.
- Session tokens and API keys are `secrets.token_urlsafe(32)`; only their SHA-256 hex digest is stored.
- Every new user has `is_admin=True`, `is_disabled=False`.
- Login failure message is always `Invalid username or password` (401).
- Service-layer guard failures raise `app.errors.ConflictError` (new) and map to 409; rule violations raise `ValidationError` → 422; unknown ids raise `NotFoundError` → 404.
- The legacy database file (`BUDGETER_DATABASE_URL`) is only ever read. Never write, move or delete it; never touch `backend/budgeter.db` in tests (use `tmp_path`).
- A model change ships with a migration in the matching Alembic tree, in the same task (see `CLAUDE.md`).
- Backend commands run from `backend/` with `.venv/bin/pytest`; frontend from `frontend/` with `npx vitest run`, `npx tsc -b`, `npm run lint`.
- Work happens on branch `user-accounts`; commit at the end of every task.

## Review Focus

Failure modes the spec implies but does not list a test for. Each has a test in the task named.

1. **Login with different case or stray spaces** (`"  Alice "` for user `alice`) — should log in. Task 3.
2. **Whole-server restore archive with hostile member names** (`../server.db`, `books/../../x.db`, `books/abc.db`, unexpected files) — rejected with 422 and nothing on disk changes. Task 7.
3. **Restoring the wrong kind of file as my books** (a `server.db`, or a books file at a migration revision this app does not know) — 422 and the current books stay intact. Task 7.
4. **A still-valid session or API key for a user who was just deleted** — 401, and no books file is re-created for the dead id. Task 6.
5. **Two registrations for the same username at once, or an over-long password** — the second gets 409 (not a 500 from the unique constraint); a 257-character password gets 422. Task 3.

---

## File Structure

Backend, new:

| File | Responsibility |
|---|---|
| `app/server_db.py` | `ServerBase`, server engine/session factory, `get_server_db`, server-tree upgrade |
| `app/server_models/__init__.py`, `user.py` | `User`, `UserSession`, `ServerSettings` |
| `app/server_migrations/` | Alembic tree for the server schema |
| `app/security.py` | Password hashing, token generation and hashing |
| `app/services/users.py` | Accounts, sessions, admin guards, server settings |
| `app/books.py` | Per-user engines, books creation, legacy claim, books-tree upgrade |
| `app/services/server_backup.py` | Whole-server zip create/validate/restore |
| `app/routers/auth.py`, `app/routers/admin.py` | HTTP layer |
| `app/schemas/auth.py`, `app/schemas/admin.py` | Request/response models |

Backend, changed: `config.py`, `db.py`, `auth.py`, `errors.py`, `main.py`, `alembic.ini`, `migrations/env.py`, every router's auth dependency, `routers/settings.py`, `routers/backup.py`, `routers/imports.py`, `services/categorization.py`, `services/backup.py`, `tests/conftest.py`. Removed: `models/api_key.py`, `services/api_key.py`, `schemas/api_key.py`, `tests/test_api_key_service.py`.

Frontend, new: `api/auth.ts`, `api/admin.ts`, `auth/AuthProvider.tsx`, `auth/userStorage.ts`, `pages/Login.tsx`, `pages/settings/AccountTab.tsx`, `pages/settings/UsersTab.tsx`, `pages/settings/ServerTab.tsx`. Changed: `api/client.ts`, `api/settings.ts`, `api/types.ts`, `App.tsx`, `components/Sidebar.tsx`, `pages/Settings.tsx`, `pages/Overview.tsx`, `pages/Categories.tsx`.

---

### Task 1: Server database, models and migration tree

**Files:**
- Create: `backend/app/server_db.py`, `backend/app/server_models/__init__.py`, `backend/app/server_models/user.py`, `backend/app/server_migrations/{env.py,script.py.mako,versions/<rev>_users_sessions_settings.py}`
- Modify: `backend/app/config.py`, `backend/alembic.ini`
- Test: `backend/tests/test_server_db.py`

**Interfaces — produces:**
- `app.config.settings.data_dir: str | None` (env `BUDGETER_DATA_DIR`) and `app.config.resolve_data_dir() -> Path | None`: the explicit setting, else the directory of the `sqlite:///` file in `database_url`, else `None` when `database_url == "sqlite://"` (in-memory test mode).
- `app.server_db`: `ServerBase`; `get_engine() -> Engine` (file `<data_dir>/server.db`, or one shared in-memory `StaticPool` engine with `create_all` applied in test mode; cached; `reset()` clears the cache); `SessionLocal() -> Session`; `get_server_db()` FastAPI dependency; `upgrade_to_head() -> None` (no-op in test mode; creates `data_dir` if missing).
- Models in `app.server_models`: `User(id, username unique, password_hash, is_admin, is_disabled, api_key_hash unique nullable, created_at)` on table `users`; `UserSession(id, user_id FK users.id, token_hash unique, created_at, expires_at)` on table `sessions`; `ServerSettings(id, registration_open default True, legacy_books_claimed default False)` on table `server_settings`.
- `alembic.ini` gains a `[server]` section with `script_location = app/server_migrations`; its `env.py` targets `ServerBase.metadata` and takes its URL from `config.attributes["db_url"]` when set, else `<resolve_data_dir()>/server.db`. CLI: `.venv/bin/alembic --name server revision --autogenerate -m "..."`.

- [ ] **Step 1: Write the failing tests** in `tests/test_server_db.py`

```python
def test_resolve_data_dir_defaults_to_the_database_files_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path}/budgeter.db")
    monkeypatch.setattr(settings, "data_dir", None)
    assert resolve_data_dir() == tmp_path

def test_resolve_data_dir_prefers_the_explicit_setting(monkeypatch, tmp_path): ...
    # data_dir=str(tmp_path / "d") -> tmp_path / "d"

def test_resolve_data_dir_is_none_for_the_in_memory_sentinel(monkeypatch): ...

def test_server_upgrade_creates_schema_and_is_idempotent(monkeypatch, tmp_path):
    # point settings at tmp_path, server_db.reset(), upgrade_to_head() twice
    # inspect(<tmp_path>/server.db) table names >= {"users", "sessions", "server_settings", "alembic_version"}

def test_new_user_defaults_to_active_admin():
    # in-memory session: add User(username="a", password_hash="x"), commit
    # assert user.is_admin is True and user.is_disabled is False and user.api_key_hash is None
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_server_db.py -v` — expect import errors.
- [ ] **Step 3: Implement** config, `server_db.py`, models, the `[server]` ini section and `env.py` (copy `app/migrations/env.py` and `script.py.mako`, swapping metadata and URL source).
- [ ] **Step 4: Generate the migration** with a scratch data dir, then read it:
  `BUDGETER_DATA_DIR=$(mktemp -d) .venv/bin/alembic --name server revision --autogenerate -m "users sessions settings"`
- [ ] **Step 5: Run** `.venv/bin/pytest -q` — all pass.
- [ ] **Step 6: Commit** `Add the server database for users, sessions and settings`

---

### Task 2: Password and token primitives

**Files:** Create `backend/app/security.py`; Test `backend/tests/test_security.py`

**Interfaces — produces:**
- `hash_password(password: str) -> str`, `verify_password(password: str, stored: str) -> bool` (False, never raises, on a malformed `stored`)
- `new_token() -> str`, `hash_token(token: str) -> str`

- [ ] **Step 1: Write the failing tests**

```python
def test_hash_round_trips():
    h = hash_password("correct horse")
    assert h.startswith("scrypt$16384$8$1$") and len(h.split("$")) == 6
    assert verify_password("correct horse", h)
    assert not verify_password("wrong horse", h)

def test_same_password_hashes_differently():
    assert hash_password("correct horse") != hash_password("correct horse")

def test_verify_rejects_malformed_hashes():
    for bad in ["", "plain", "scrypt$1$2", "bcrypt$16384$8$1$00$00"]:
        assert verify_password("x", bad) is False

def test_tokens_are_unique_and_hash_is_sha256_hex():
    a, b = new_token(), new_token()
    assert a != b and len(a) >= 43
    assert hash_token(a) == hashlib.sha256(a.encode()).hexdigest()
```

- [ ] **Step 2: Run** — expect failure. **Step 3: Implement** with `hashlib.scrypt` (`dklen=32`) and `hmac.compare_digest`. **Step 4: Run** — pass. **Step 5: Commit** `Add password hashing and token helpers`

---

### Task 3: Users service

**Files:** Create `backend/app/services/users.py`; Modify `backend/app/errors.py` (add `ConflictError`, `AuthError`); Test `backend/tests/test_users_service.py`

**Interfaces — consumes:** Task 1 models, Task 2 helpers. All functions take a server-database `Session` as `db`.

**Produces:**
- `normalize_username(raw: str) -> str` (trim, lower; `ValidationError` naming the rule)
- `create_user(db, username: str, password: str) -> User` (`ConflictError("Username is already taken")`, including when the unique constraint fires on commit)
- `register(db, username, password) -> User` (`AuthError("Registration is closed")` when closed and a user exists)
- `authenticate(db, username, password) -> User` (`AuthError("Invalid username or password")` for unknown, wrong or disabled)
- `create_session(db, user) -> str` (raw token); `resolve_session(db, token: str, now: datetime | None = None) -> User | None` (None for unknown, expired or disabled; slides expiry per Global Constraints); `delete_session(db, token)`; `delete_user_sessions(db, user_id, keep_token: str | None = None)`; `purge_expired_sessions(db)`
- `resolve_api_key(db, key: str) -> User | None` (None when disabled); `regenerate_api_key(db, user) -> str`
- `change_password(db, user, current: str, new: str, keep_token: str | None)` (`AuthError` on a wrong current password; ends other sessions)
- `list_users(db) -> list[User]` ordered by id; `get_user(db, user_id) -> User`
- `update_user(db, user_id, *, is_admin: bool | None = None, is_disabled: bool | None = None, password: str | None = None) -> User` — disabling deletes that user's sessions
- `delete_user(db, user_id) -> None` — removes sessions and the row (books removal is wired in Task 6)
- `get_settings(db) -> ServerSettings` (creates the row on first use); `set_registration_open(db, value: bool) -> ServerSettings`; `has_users(db) -> bool`
- Guard, shared by `update_user` and `delete_user`: `ConflictError("The last active admin can't be demoted, disabled or deleted")` when the change would leave no user with `is_admin and not is_disabled`.

- [ ] **Step 1: Write the failing tests** (fixture `sdb`: a fresh in-memory server session)

```python
def test_create_user_normalizes_and_hashes(sdb):
    u = users.create_user(sdb, "  Alice ", "password1")
    assert u.username == "alice" and u.is_admin and verify_password("password1", u.password_hash)

@pytest.mark.parametrize("name", ["ab", "a" * 33, "has space", "ünï", ""])
def test_rejects_bad_usernames(sdb, name): ...          # ValidationError

@pytest.mark.parametrize("pw", ["short", "x" * 257])
def test_rejects_bad_passwords(sdb, pw): ...            # ValidationError

def test_duplicate_username_is_a_conflict_whatever_the_case(sdb): ...   # "ALICE" after "alice"

def test_unique_constraint_race_is_a_conflict_not_a_crash(sdb, monkeypatch):
    # make the pre-insert existence check report "free", insert a clashing row -> ConflictError

def test_authenticate_accepts_case_and_whitespace_variants(sdb):
    users.create_user(sdb, "alice", "password1")
    assert users.authenticate(sdb, "  Alice ", "password1").username == "alice"

def test_authenticate_failures_share_one_message(sdb):
    # unknown user, wrong password, disabled user -> AuthError, str == "Invalid username or password"

def test_registration_open_until_closed_and_always_open_with_no_users(sdb):
    users.set_registration_open(sdb, False)
    users.register(sdb, "first", "password1")           # no users yet: allowed
    with pytest.raises(AuthError): users.register(sdb, "second", "password1")

def test_session_resolves_slides_and_expires(sdb):
    t = users.create_session(sdb, u); t0 = now
    assert users.resolve_session(sdb, t, now=t0 + timedelta(days=2)) is u
    # expiry is now >= t0 + 32 days; resolve at t0 + 33 days -> None; unknown token -> None

def test_disabling_ends_sessions_and_blocks_the_api_key(sdb): ...
def test_regenerated_api_key_replaces_the_old_one(sdb): ...
def test_change_password_needs_current_and_ends_other_sessions(sdb): ...

def test_last_active_admin_is_protected(sdb):
    a = create("a"); b = create("b"); users.update_user(sdb, b.id, is_admin=False)
    for change in (dict(is_admin=False), dict(is_disabled=True)):
        with pytest.raises(ConflictError): users.update_user(sdb, a.id, **change)
    with pytest.raises(ConflictError): users.delete_user(sdb, a.id)
    users.update_user(sdb, b.id, is_admin=True); users.delete_user(sdb, a.id)   # now allowed

def test_a_disabled_admin_does_not_count_as_active(sdb): ...
```

- [ ] **Step 2: Run** — fail. **Step 3: Implement.** **Step 4: Run** `.venv/bin/pytest -q` — pass. **Step 5: Commit** `Add the users service: accounts, sessions and admin guards`

---

### Task 4: Authentication dependency, auth endpoints and API keys

**Files:**
- Create: `backend/app/routers/auth.py`, `backend/app/schemas/auth.py`, `backend/tests/test_auth_router.py`
- Modify: `backend/app/auth.py`, `backend/app/main.py`, `backend/app/routers/settings.py`, all routers (`require_api_key` → `current_user`), `backend/tests/conftest.py`, `backend/tests/test_auth.py`, `backend/tests/test_settings_router.py`
- Delete: `backend/app/services/api_key.py`, `backend/app/schemas/api_key.py`, `backend/tests/test_api_key_service.py` (the `ApiKey` model and table go in Task 5)

**Interfaces — produces:**
- `app.auth.current_user(request, credentials, sdb=Depends(get_server_db)) -> User`: bearer key first, then the `budgeter_session` cookie; 401 `Not authenticated` otherwise. Stores the raw session token on `request.state.session_token` (None for key auth). `app.auth.require_admin(user=Depends(current_user)) -> User`: 403 `Admin access required`.
- `app.auth.set_session_cookie(response, request, token)`, `clear_session_cookie(response)`.
- Endpoints (spec table): `GET /api/auth/status`, `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout` (204), `GET /api/auth/me`, `POST /api/auth/password` (204). Bodies: `{username, password}`; password change `{current_password, new_password}`. `UserRead = {id, username, is_admin}`. Error mapping: `AuthError` → 401 for login and password change, 403 for closed registration.
- `GET /api/settings/api-key` → `{has_key: bool}`; `POST /api/settings/api-key/regenerate` → `{api_key: str}`.
- `main.py` lifespan also calls `server_db.upgrade_to_head()` and `users.purge_expired_sessions`.
- `conftest.py`: a `server_session` fixture (in-memory server DB, `get_server_db` overridden); `client` seeds user `tester` whose `api_key_hash = hash_token("test-api-key")`, exposed as fixture `test_user`; `auth_headers` unchanged. `get_db` override unchanged for now.

- [ ] **Step 1: Write the failing tests** in `tests/test_auth_router.py`

```python
def test_status_reports_no_users_then_users(client): ...    # uses a client with no seeded user
def test_register_logs_in_and_me_returns_the_user(anon):
    r = anon.post("/api/auth/register", json={"username": "Alice", "password": "password1"})
    assert r.status_code == 201 and r.json() == {"id": ANY, "username": "alice", "is_admin": True}
    cookie = r.headers["set-cookie"]
    assert "budgeter_session=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert anon.get("/api/auth/me").json()["username"] == "alice"
def test_register_conflict_is_409_and_bad_input_422(anon): ...
def test_register_is_403_when_closed(anon): ...
def test_login_wrong_password_unknown_user_and_disabled_are_the_same_401(anon): ...
def test_logout_ends_the_session(anon): ...                 # me -> 401 afterwards
def test_password_change_keeps_this_session_and_ends_others(anon): ...
def test_api_key_is_shown_once_and_replaces_the_old(anon):
    # GET -> {"has_key": False}; regenerate -> key; GET -> {"has_key": True}
    # Bearer key works on /api/auth/me without a cookie; regenerate again -> old key 401
def test_env_default_key_no_longer_authenticates(anon): ... # Bearer dev-local-api-key -> 401
def test_non_admin_gets_403_from_require_admin(anon): ...   # throwaway route, as tests/test_auth.py does
```

(`anon` = a `TestClient` with the overrides but no seeded user.)

- [ ] **Step 2: Run** — fail. **Step 3: Implement**, replacing `require_api_key` across routers with `current_user`. **Step 4: Update** `test_auth.py` and `test_settings_router.py` to the new behaviour. **Step 5: Run** `.venv/bin/pytest -q` — all pass. **Step 6: Commit** `Add login, sessions and per-user API keys`

---

### Task 5: Per-user books

**Files:**
- Create: `backend/app/books.py`, `backend/app/migrations/versions/<rev>_drop_api_key_table.py`, `backend/tests/test_books.py`, `backend/tests/test_isolation.py`
- Modify: `backend/app/db.py`, `backend/app/migrations/env.py`, `backend/app/models/__init__.py`, `backend/app/main.py`, `backend/app/services/categorization.py`, `backend/app/routers/imports.py`, `backend/app/routers/auth.py`, `backend/tests/conftest.py`, `backend/tests/test_db_migrations.py`
- Delete: `backend/app/models/api_key.py`

**Interfaces — produces (`app.books`):**
- `books_path(user_id: int) -> Path` (`<data_dir>/books/<id>.db`)
- `session_for(user_id: int) -> Session` — engine cached per id; creates and migrates the file if it is missing. In test mode each id gets its own in-memory `StaticPool` engine with `Base.metadata.create_all`.
- `create_books(user_id)`, `dispose(user_id)`, `dispose_all()`, `delete_books(user_id)` (dispose, then unlink if present)
- `upgrade(path: Path) -> None` — books Alembic tree against one file; `upgrade_all(user_ids: Iterable[int])`
- `claim_legacy_books(sdb, user) -> bool` — per the spec's "Existing data": copies via `services.backup.create_backup_bytes`, upgrades, carries a legacy `api_key.key` over as `user.api_key_hash` (read with raw SQL before the upgrade drops the table), sets `legacy_books_claimed`. Returns False and does nothing when already claimed, the legacy file is missing, or in test mode.
- `app.db.get_db(user: User = Depends(current_user))` yields `books.session_for(user.id)`. `app.db.engine`, `SessionLocal` and `upgrade_to_head` are removed; `main.py` calls `server_db.upgrade_to_head()` then `books.upgrade_all(...)`, and purges history per user.
- `categorization.run_categorization_in_background(user_id: int, transaction_ids: list[int] | None = None)`; the three call sites in `routers/imports.py` pass `user.id`.
- `migrations/env.py` URL precedence: `config.attributes["db_url"]`, then `-x db=<path>`, then `settings.database_url`.
- `routers/auth.py` register: after creating the user, `claim_legacy_books(sdb, user)` or else `create_books(user.id)`.
- `conftest.py`: `db_session` becomes `books.session_for(test_user.id)` and the `get_db` override is dropped; a `files` fixture points `settings` at `tmp_path` (file-backed mode) and resets the engine caches before and after.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_books.py
def test_session_for_creates_and_migrates_a_missing_file(files): ...
    # books_path(7) exists afterwards and has "accounts" and "alembic_version", no "api_key"
def test_each_user_gets_a_separate_file(files): ...
def test_delete_books_removes_the_file_and_tolerates_a_missing_one(files): ...
def test_first_user_claims_a_copy_of_the_legacy_database(files, legacy_db):
    # legacy_db: a tmp budgeter.db at the previous books head, one account "Main", api_key row "legacy-key"
    before = legacy_db.read_bytes()
    assert books.claim_legacy_books(sdb, first) is True
    assert account names in books.session_for(first.id) == ["Main"]
    assert first.api_key_hash == hash_token("legacy-key")
    assert legacy_db.read_bytes() == before              # never modified
def test_second_user_does_not_claim(files, legacy_db): ...   # returns False, empty books
def test_claim_without_a_legacy_file_is_a_no_op(files): ...
def test_legacy_database_at_an_old_revision_is_upgraded_on_claim(files): ...

# tests/test_isolation.py  (file-backed, two registered users, two clients)
def test_users_cannot_see_or_fetch_each_others_data(files):
    # alice creates an account and a category; bob lists both -> []
    # bob GET/PATCH/DELETE /api/accounts/<alice's id> -> 404; bob's own first account may reuse the same id
def test_background_categorization_runs_against_the_importers_books(files): ...
```

- [ ] **Step 2: Run** — fail.
- [ ] **Step 3: Implement** `books.py`, the `get_db` switch, `env.py`, and the background-task signature.
- [ ] **Step 4: Remove the `ApiKey` model and generate the books migration**, then read it:
  `BUDGETER_DATABASE_URL=sqlite:///$(mktemp -d)/scratch.db .venv/bin/alembic upgrade head && ... alembic revision --autogenerate -m "drop api key table"` (same scratch URL for both commands).
- [ ] **Step 5: Rewrite** `tests/test_db_migrations.py` for `books.upgrade` and `server_db.upgrade_to_head` (fresh file, idempotent, test-mode no-op).
- [ ] **Step 6: Run** `.venv/bin/pytest -q` — all pass, including the untouched router tests.
- [ ] **Step 7: Commit** `Give each user their own books file`

---

### Task 6: Admin endpoints and account deletion

**Files:** Create `backend/app/routers/admin.py`, `backend/app/schemas/admin.py`, `backend/tests/test_admin_router.py`; Modify `backend/app/routers/auth.py`, `backend/app/main.py`

**Interfaces — produces:**
- Admin endpoints per the spec table, all behind `require_admin`. `AdminUserRead = {id, username, is_admin, is_disabled, created_at}`; create body `{username, password}` → 201; PATCH body any of `{is_admin, is_disabled, password}`; `GET/PATCH /api/admin/settings` ↔ `{registration_open}`.
- `DELETE /api/auth/me` body `{password}` → 204, clears the cookie; 401 on a wrong password.
- Both delete paths call `users.delete_user` then `books.delete_books(user_id)`. Admin-created users get `books.create_books`.

- [ ] **Step 1: Write the failing tests**

```python
def test_admin_endpoints_need_admin(two_users): ...          # non-admin -> 403, anonymous -> 401
def test_list_create_and_patch_users(admin): ...
def test_reset_password_lets_the_user_log_in_with_the_new_one(admin): ...
def test_disable_blocks_login_session_and_key_and_enable_restores(admin): ...
def test_last_admin_guards_return_409(admin): ...            # demote, disable, delete, DELETE /auth/me
def test_delete_user_removes_their_books_file(files, admin): ...
def test_delete_me_needs_the_password(files, two_users): ...
def test_deleted_users_session_and_key_get_401_and_no_books_reappear(files, two_users):
    # bob holds a cookie client and a key; admin deletes bob
    # bob GET /api/accounts with each -> 401; books.books_path(bob_id).exists() is False
def test_closing_registration_blocks_register_but_not_admin_create(admin): ...
```

- [ ] **Step 2: Run** — fail. **Step 3: Implement.** **Step 4: Run** `.venv/bin/pytest -q` — pass. **Step 5: Commit** `Add admin user management and account deletion`

---

### Task 7: Backup and restore

**Files:** Create `backend/app/services/server_backup.py`, `backend/tests/test_server_backup.py`; Modify `backend/app/services/backup.py`, `backend/app/routers/backup.py`, `backend/app/routers/admin.py`, `backend/tests/test_backup_router.py`

**Interfaces — produces:**
- `services.backup.validate_books_bytes(data: bytes) -> None`: `validate_sqlite_bytes` plus: has `alembic_version` and `accounts`, has no `users` table, and its revision is one the books tree knows (`ScriptDirectory.get_revision`). `ValidationError` otherwise.
- `/api/backup` (per user): download snapshots `books.books_path(user.id)`; restore = validate → `books.dispose` → `write_backup_bytes` → `books.upgrade`.
- `services.server_backup.create_archive() -> bytes` — zip with `server.db` and `books/<id>.db` for every existing user, each via `create_backup_bytes`.
- `services.server_backup.restore_archive(data: bytes) -> None` — member names must be exactly `server.db` or match `^books/\d+\.db$`, and `server.db` is required; validate every member (`validate_books_bytes` for books; server needs a `users` table); stage all into a temp directory inside `data_dir`; then dispose every engine, `os.replace` each file, delete books files not in the archive, run both upgrades. Any failure before the swap raises `ValidationError` and leaves the disk unchanged.
- `GET /api/admin/backup` (filename `budgeter-server-backup-<date>.zip`), `POST /api/admin/backup/restore` (204; 422 on `ValidationError`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_backup_router.py (rewritten on the `files` fixture)
def test_download_then_restore_round_trips_my_books(files): ...
def test_restore_does_not_touch_another_users_books(files): ...
def test_restore_upgrades_an_older_books_file(files): ...
@pytest.mark.parametrize("kind", ["not_sqlite", "server_db", "unknown_revision", "no_alembic_version"])
def test_restore_rejects_the_wrong_file_and_keeps_current_books(files, kind):
    # 422; the account created before the attempt is still listed

# tests/test_server_backup.py
def test_archive_holds_server_db_and_every_users_books(files): ...     # namelist == {"server.db", "books/1.db", "books/2.db"}
def test_restore_round_trips_users_and_books_and_drops_extra_books(files):
    # archive with 2 users; add a 3rd; restore -> 3rd user and books/3.db are gone, the others' data is back
@pytest.mark.parametrize("name", ["../server.db", "books/../../x.db", "books/abc.db", "notes.txt", "/etc/x.db"])
def test_restore_rejects_hostile_or_unexpected_members(files, name):
    # ValidationError; every file under data_dir has the same bytes as before
def test_restore_with_one_corrupt_books_member_changes_nothing(files): ...
def test_restore_without_server_db_is_rejected(files): ...
def test_whole_server_backup_endpoints_are_admin_only(files): ...
```

- [ ] **Step 2: Run** — fail. **Step 3: Implement.** **Step 4: Run** `.venv/bin/pytest -q` — pass. **Step 5: Commit** `Scope backup to the user's books and add whole-server backup`

---

### Task 8: Frontend login and session handling

**Files:**
- Create: `frontend/src/api/auth.ts`, `frontend/src/auth/AuthProvider.tsx`, `frontend/src/auth/userStorage.ts`, `frontend/src/pages/Login.tsx`, tests beside each
- Modify: `frontend/src/api/client.ts`, `frontend/src/api/types.ts`, `frontend/src/App.tsx`, `frontend/src/components/Sidebar.tsx` (+ test), `frontend/src/pages/Overview.tsx`, `frontend/src/pages/Categories.tsx` (+ tests), `frontend/src/styles/global.css`

**Interfaces — produces:**
- `types.ts`: `AuthUser { id: number; username: string; is_admin: boolean }`, `AuthStatus { registration_open: boolean; has_users: boolean }`.
- `authApi`: `status()`, `me()`, `login(username, password)`, `register(username, password)`, `logout()`, `changePassword(current, next)`, `deleteMe(password)`. `me()` and `status()` are called with `{ silent: true }`.
- `client.ts`: every request sends `credentials: "include"`; the API-key storage, `getApiKey`, `setApiKey` and the `Authorization` header are removed; `setUnauthorizedListener(fn | null)` is called on any 401 except from `/api/auth/login`, and a 401 that triggers it shows no error toast.
- `AuthProvider` + `useAuth(): { user: AuthUser; logout(): Promise<void>; refresh(): Promise<void> }`. Renders nothing while `/auth/me` is pending, `<Login />` when logged out, children when logged in. `App.tsx` wraps the existing layout in it.
- `userStorage(userId)`: `get(key)`, `set(key, value)`, `remove(key)` over `localStorage` key `budgeter.u<id>.<key>`. Overview uses key `overview.budget`, Categories `categories.selected` (replacing the Round 1 keys).
- `Login`: one form with a Log in / Create account switch, shown only when `registration_open || !has_users`. With `!has_users` it opens on Create account with the note `The first account takes over this server's existing data.` Failed submits show the server's message inline.
- Sidebar: brand subtitle shows `user.username`; a `Log out` control below the nav.

- [ ] **Step 1: Write the failing tests**

```tsx
// AuthProvider.test.tsx
it("renders nothing while the session check is pending")
it("shows the login screen when /auth/me is 401")
it("renders the app when a user is returned")
it("returns to the login screen when any later request reports 401")
it("logout calls the API and shows the login screen")
// Login.test.tsx
it("logs in and hands the user to the provider")
it("shows the server's message on a failed login")       // "Invalid username or password"
it("hides Create account when registration is closed and users exist")
it("opens on Create account with the takeover note when there are no users")
it("registers and enters the app")
// client.test.ts
it("sends credentials and no Authorization header")
it("notifies the unauthorized listener on 401 without a toast, but not for /api/auth/login")
// userStorage.test.ts
it("keeps two users' values apart")
// Sidebar.test.tsx: shows the username and a Log out control
// Overview.test.tsx / Categories.test.tsx: STORAGE_KEY becomes budgeter.u1.overview.budget / budgeter.u1.categories.selected, rendered inside a stub auth context for user id 1
```

- [ ] **Step 2: Run** `npx vitest run` — fail. **Step 3: Implement.** **Step 4: Run** `npx vitest run && npx tsc -b && npm run lint` — clean. **Step 5: Commit** `Add the login screen and session handling`

---

### Task 9: Frontend settings — Account, Users, Server

**Files:**
- Create: `frontend/src/api/admin.ts`, `frontend/src/pages/settings/{AccountTab,UsersTab,ServerTab}.tsx` with tests
- Modify: `frontend/src/pages/Settings.tsx`, `frontend/src/api/settings.ts`, `frontend/src/api/types.ts`

**Interfaces — produces:**
- `types.ts`: `AdminUser { id; username; is_admin; is_disabled; created_at }`.
- `adminApi`: `listUsers()`, `createUser(username, password)`, `updateUser(id, patch)`, `deleteUser(id)`, `getSettings()`, `updateSettings({ registration_open })`, `downloadBackup()`, `restoreBackup(file)`.
- `settingsApi.getApiKey()` → `{ has_key: boolean }`.
- `Settings.tsx`: the `ApiKeyTab` is removed; tab order is Account, Categories, Categorization rules, Backup & restore, History, then Users and Server only when `user.is_admin`. Default tab `account`.
- **Account:** change-password form (current, new, confirm; mismatch blocks submit); API key card showing `No key yet` or `A key is set`, with Regenerate (same confirm text as today) revealing the new key once with the note `Copy it now — it won't be shown again.`; a Delete my account card requiring the password and a confirm.
- **Users:** table of username, admin, status, created; row actions Disable/Enable, Make admin/Remove admin, Reset password (prompts for the new one), Delete (confirm naming the user and that their data is removed). The current user's row is labelled `you`. A create-user form above the table. Server 409 messages surface through the existing toast.
- **Server:** an `Allow new registrations` checkbox saved on change; whole-server Download and Restore cards modelled on `BackupTab`, with the restore confirm `This replaces every user's data and accounts with the archive. You may need to log in again. Continue?`
- `BackupTab` copy changes from "the full database" to "your books".

- [ ] **Step 1: Write the failing tests**

```tsx
// Settings.test.tsx
it("hides the Users and Server tabs from a non-admin")
it("shows them to an admin")
// AccountTab.test.tsx
it("blocks a password change when the confirmation differs")
it("submits the current and new password")
it("reveals a regenerated key once, and only status after a reload")
it("deletes the account only after the password is entered and confirmed")
// UsersTab.test.tsx
it("lists users and marks the current one")
it("creates a user and refreshes the list")
it("toggles disabled and admin through PATCH")
it("asks before deleting and names the user")
// ServerTab.test.tsx
it("saves the registration toggle")
it("warns before a whole-server restore and does nothing when cancelled")
```

- [ ] **Step 2: Run** — fail. **Step 3: Implement.** **Step 4: Run** `npx vitest run && npx tsc -b && npm run lint && npm run build` — clean. **Step 5: Commit** `Add account, user and server settings`

---

### Task 10: Documentation and end-to-end check

**Files:** Modify `CLAUDE.md`, `README.md`, `docs/requirements.md`, `docs/container.md`, `mcp_adapter/README.md`, `Containerfile` (comment only, if it describes the single file)

- [ ] **Step 1: Update the docs** per the spec's Documentation section. `CLAUDE.md` must state: the two Alembic trees and which models belong to each; the two autogenerate commands (books against a scratch URL, server with `--name server`); that dev data now lives in `backend/server.db` and `backend/books/<id>.db`; and that `backend/budgeter.db` is the read-only legacy source — still never to be removed or reset by a test workflow.
- [ ] **Step 2: End-to-end check against a scratch copy**, never the live file:

```bash
SCRATCH=$(mktemp -d) && sqlite3 backend/budgeter.db ".backup $SCRATCH/budgeter.db"
cd backend && BUDGETER_DATABASE_URL=sqlite:///$SCRATCH/budgeter.db .venv/bin/uvicorn app.main:app --port 8000
cd frontend && npm run dev
```

In the browser: register the first user and confirm the existing accounts and budgets appear; log out and in; register a second user and confirm empty books; as the second user confirm the first user's data is absent; disable the second user from the first and confirm their login fails; regenerate an API key and call `curl -H "Authorization: Bearer <key>" localhost:8000/api/accounts`; download and restore a personal backup; download a whole-server backup. Confirm `$SCRATCH/budgeter.db` is byte-identical to its starting copy.

- [ ] **Step 3: Run everything** — `.venv/bin/pytest -q`; `npx vitest run && npx tsc -b && npm run lint && npm run build`; `mcp_adapter` tests.
- [ ] **Step 4: Commit** `Document user accounts and the per-user data layout`

# Shared budgets — design

Date: 2026-10-19

## Goal

Several users on one server keep a budget together (e.g. a household). The
shared budget has its own category tree and monthly budgeted amounts. Each
member maps categories from their own books onto the shared categories, and
the shared budget shows, per shared category and month, the budget, the
combined actual, and each member's share of that actual.

Members see **totals plus a per-member split** — never another member's
transactions.

## Decisions

| Topic | Decision |
|---|---|
| Visibility | Totals + per-member split per shared category/month. No transaction drill-down. |
| Membership | Any member adds users directly (no invite/accept). All members are equal: any member can rename, delete, edit members, shared categories and amounts. A member's mappings are edited only by that member. |
| Mapping cardinality | Many of my categories → one shared category; each of my categories maps to at most one shared category per shared budget. |
| Parents | Mapping a parent includes its subcategories; a descendant with its own link uses that link instead (most specific wins). |
| Splits | Counted per split line (`Split.category_id`). |
| Ratio | Full amount, no percentage. |
| Accounts | No account narrowing on mappings. |
| Storage | Registry in `server.db`; one file per shared budget (`shared/<id>.db`); mappings in each member's books. |
| Actuals | Stored as a tally in the shared file, recomputed per member after each relevant books commit; rebuilt on startup, restore and join. Viewing never reads members' books. |

## 1. Storage and data model

### Registry — `server.db` (new server migration)

- `shared_budgets(id INTEGER PK AUTOINCREMENT, name VARCHAR(200) NOT NULL, created_at DATETIME NOT NULL)` — `sqlite_autoincrement` so an id (and so a file name) is never reused.
- `shared_budget_members(shared_budget_id FK→shared_budgets, user_id FK→users, PRIMARY KEY(shared_budget_id, user_id))`.

Models in `app/server_models/shared_budget.py`.

### Shared budget file — `shared/<id>.db` (new schema)

A third schema with its own declarative base `SharedBase` (`app/shared_db.py`),
models package `app/shared_models/`, Alembic tree `app/shared_migrations/`
(selected with `alembic --name shared`), and an engine cache
`app/shared_books.py` mirroring `app/books.py` (`shared_path`, `session_for`,
`upgrade`, `upgrade_all`, `create`, `delete`, `dispose`, `dispose_all`,
`replace_all`). NullPool engines and the existing `MIGRATION_LOCK` /
`run_upgrade` are reused.

Tables:

- `shared_categories(id PK, name VARCHAR(200) NOT NULL, parent_id FK→shared_categories NULL, sort_order INT NOT NULL DEFAULT 0, is_income BOOL NOT NULL DEFAULT 0, archived_at DATETIME NULL)`.
- `shared_budget_amounts(id PK, shared_category_id FK ON DELETE CASCADE, year INT, month INT, amount NUMERIC(12,2), UNIQUE(shared_category_id, year, month))`.
- `member_tallies(id PK, user_id INT NOT NULL, shared_category_id FK ON DELETE CASCADE, year INT, month INT, amount NUMERIC(12,2), UNIQUE(user_id, shared_category_id, year, month))` — raw signed sum of the member's split amounts (ledger sign: spending negative). The report applies the sign convention. `user_id` is a plain integer; this file is not anyone's books.

Foreign keys are enforced per connection (as `server_db` does).

### Mappings — each member's books (new books migration)

- `shared_category_links(id PK, category_id FK→categories ON DELETE CASCADE, shared_budget_id INT NOT NULL, shared_category_id INT NOT NULL, UNIQUE(shared_budget_id, category_id))`.

`shared_budget_id` and `shared_category_id` point into other databases and are
plain integers. No user id is stored — the file is the user.

### Lifecycle

- **Create**: registry row + creator as member + requested members; create and migrate `shared/<id>.db`; recompute each member.
- **Last member leaves / is removed / is deleted**: delete registry rows and the file.
- **User deleted** (`users.delete_user`): drop their memberships and their `member_tallies` rows in every shared file they were in; apply the last-member rule.
- **Shared category deleted**: amounts and tallies cascade within the shared file. Members' links to it become stale (skipped by the recompute, pruned on the next links edit).

### Backup / restore

- Whole-server archive (`services/server_backup.py`) includes `shared/<id>.db` members; restore validates (shared schema revision known, integrity check) and replaces the `shared/` directory to hold exactly the archived files, then runs `rebuild_all()`. Archives without `shared/` entries (older archives) restore to no shared files; registry rows that have no file get a fresh file on rebuild.
- Single-user books restore carries that user's links; afterwards `recompute_member(user_id)`.

### Startup (`main.py` lifespan)

After `server_db.upgrade_to_head()` and `books.upgrade_all()`: `shared_books.upgrade_all(registered ids)` (creating missing files), then `shared_tally.rebuild_all()`.

### CLAUDE.md

Add the third schema to the table (Shared — shared categories, budgeted amounts, member tallies — `app/shared_models/`, `SharedBase`, `app/shared_migrations/`, `shared/<id>.db`), the `--name shared` autogenerate commands, and amend the placement rule: data budgeted with by several users together goes in its shared budget file; who belongs to a shared budget goes in the server schema.

## 2. Tally maintenance and the report

### Commit hook — `app/services/shared_tally.py`

`books.session_for(user_id)` stores `user_id` in `session.info` and the session
carries two listeners (registered once on a books-session class or per session):

- `after_flush`: if any new/dirty/deleted object is a `Transaction`, `Split`, `Category` or `SharedCategoryLink`, set `session.info["shared_tally_dirty"] = True`.
- `after_commit`: if the flag is set, clear it and call `recompute_member(user_id)`.

Bulk `session.execute(update/delete(...))` statements on those tables don't pass through `after_flush`; any such call sites must set the flag explicitly (the implementation plan audits for them), or an `after_bulk_update`/`after_bulk_delete` listener sets it.

The recompute runs synchronously after the commit. Failures are logged, not raised: the member's own write already succeeded, and the next relevant commit or a restart repairs the tally.

### `recompute_member(user_id)`

1. Memberships from `server.db`.
2. For each shared budget the user belongs to:
   - Load the user's links for that budget from their books; ignore links whose shared category doesn't exist (or is the wrong budget).
   - Expand: each linked category maps itself and all descendants, except descendants that carry their own link for this budget (most specific link wins).
   - One grouped query over the user's books: `SUM(Split.amount)` joined to `Transaction`, `WHERE Split.category_id IN (expanded)`, grouped by category, year, month; fold category → shared category in Python. No transaction-type filter (same as `budgets._actuals_for_category`).
   - In the shared file, in one transaction under that file's lock: delete the user's `member_tallies` rows, insert the new ones.

`rebuild_all()` recomputes every member of every registered budget.
Triggered: startup, after whole-server restore. `recompute_member` is also
called after a single-user books restore and when a user is added to a budget.
When a user is removed from a budget, their tally rows in that file are deleted.

### Report — `GET /api/shared-budgets/{id}/report?year=&through_month=`

Reads only the shared file and usernames from `server.db`.

- Rows follow the shared category tree (non-archived categories, plus archived ones that have amounts or tallies in the year), parents rolled up from children via `budget_rollup.sum_monthly`, with `depth`.
- Each row: monthly `(budgeted, actual)`, `ytd_diff`, `has_budget`, `is_income`, built with `budget_rollup.build_row`; plus `members: [{user_id, username, monthly: {month: actual}, ytd_actual}]`.
- Sign convention as the existing report: actual = −sum for expense categories; income categories (own or inherited `is_income`) flip so deposits read positive.
- Members whose tally is all zero still appear (with zeros) so the split is complete.

## 3. API and UI

### API — `app/routers/shared_budgets.py`, service `app/services/shared_budgets.py`, schemas `app/schemas/shared_budget.py`

Every route requires the caller to be a member; otherwise `NotFoundError` (404 via `errors.py`). Validation errors use the existing domain error classes.

| Method & path | Behaviour |
|---|---|
| `GET /api/shared-budgets` | Budgets the caller is a member of: `{id, name, members:[{user_id, username, is_disabled}]}` |
| `POST /api/shared-budgets` `{name, member_ids}` | Create; caller always included; unknown or disabled ids rejected. |
| `PATCH /api/shared-budgets/{id}` `{name}` | Rename. |
| `DELETE /api/shared-budgets/{id}` | Delete registry rows and file. |
| `PUT /api/shared-budgets/{id}/members` `{user_ids}` | Replace the member list. Must be non-empty (removing yourself is allowed if others remain; to remove everyone, delete). Newly added users must exist and be enabled; added → recompute; removed → tally rows deleted. |
| `GET /api/users/directory` | `[{id, username}]` of enabled users, for any logged-in user. No admin fields. |
| `GET /api/shared-budgets/{id}/categories` | The shared category tree. |
| `POST /api/shared-budgets/{id}/categories` `{name, parent_id?, is_income?}` | Create. |
| `PATCH /api/shared-budgets/{id}/categories/{cid}` `{name?, parent_id?, sort_order?, is_income?, archived?}` | Update; reject cycles. |
| `DELETE /api/shared-budgets/{id}/categories/{cid}` | Delete; rejected if it has children. |
| `GET /api/shared-budgets/{id}/amounts?year=` | `[{shared_category_id, month, amount}]`. |
| `PUT /api/shared-budgets/{id}/amounts` `{year, lines:[{shared_category_id, month, amount}]}` | Upsert; a `null` amount removes the row. |
| `GET /api/shared-budgets/{id}/links` | The caller's links for this budget (stale ones omitted). |
| `PUT /api/shared-budgets/{id}/links` `{links:[{category_id, shared_category_id}]}` | Replace the caller's links for this budget. Each `category_id` must exist in the caller's books and appear once; each `shared_category_id` must exist in this budget. Committed through the caller's books session, so the hook recomputes. |
| `GET /api/shared-budgets/{id}/report?year=&through_month=` | Section 2. |

### UI (`frontend/src`)

- Sidebar entry **Shared budgets** → `pages/SharedBudgets.tsx` (list + create dialog with member picker from the directory) and `pages/SharedBudget.tsx` (one budget) with tabs:
  1. **Report** — the Budgets report layout; each category row expands to per-member rows (mirroring per-account rows today).
  2. **Setup** — name, members (picker; disabled users shown but not addable), shared category tree editor, monthly amounts grid (reusing Budgets amount-entry components where they fit), delete budget.
  3. **My mappings** — each shared category with a multi-select of the caller's categories (`CategoryCombobox`); a category already mapped to another shared category in this budget is disabled there.
- API client `api/sharedBudgets.ts`, types in `api/types.ts`.

### Out of scope

History/undo for shared-budget edits and for link edits; MCP adapter tools; notifications; account-narrowed mappings; percentage mappings; invite/accept.

## 4. Edge cases

- **Disabled user**: stays a member; tally frozen and visible. Not addable.
- **Deleted user**: memberships and tally rows removed; last member → budget deleted.
- **Archived books category**: still linked, still counts.
- **Deleted books category**: link cascades; recompute drops it.
- **Reparented books category**: `Category` change triggers recompute; it now follows its new ancestor's link unless it has its own.
- **Shared category deleted**: amounts/tallies cascade; members' links skipped, pruned on next links edit.
- **Archived shared category**: hidden in My mappings; shown in the report only for years with data.
- **Missing shared file**: created and migrated on startup; tallies refilled by `rebuild_all`. Files with no registry row are ignored (and dropped by a whole-server restore).
- **Concurrent recomputes**: per-shared-file lock; each member only rewrites their own rows.
- **In-memory test mode (`sqlite://`)**: shared files use per-budget in-memory `StaticPool` engines with `create_all`, mirroring books.

## 5. Testing

Backend (pytest):

- `test_shared_tally.py`: descendant expansion with most-specific link winning; split-level sums; income sign in the report; full replace of only the member's own rows; stale links skipped; recompute triggered through the commit hook (not direct calls) on transaction create/edit/delete, split edit, category reparent/delete, links edit; no recompute on unrelated commits.
- Rebuilds: startup, whole-server restore (archive includes `shared/`), single-user restore, member added.
- `test_shared_budgets_router.py`: non-member 404 on every route; member list can't become empty; create/rename/delete; categories CRUD incl. cycle and has-children rejections; amounts upsert/remove; links validation (unknown category, duplicate category, foreign shared category); report shape incl. per-member split.
- User deletion cleans memberships, tallies, and last-member budgets.
- `/api/users/directory` returns only `id` and `username` of enabled users.
- `test_isolation.py`: the report exposes only per-category monthly totals per member; a member cannot read or edit another member's links.
- `test_db_migrations.py`: new books migration, new server migration, the `shared` tree upgrades from empty to head.

Frontend (Vitest + RTL): shared budget list/create; My mappings disables categories already mapped elsewhere; Report renders per-member rows.

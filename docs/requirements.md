# Personal Finance Tracker — Requirements Document

## 1. Purpose & Scope

Replace the current workflow (bank statement → GnuCash import/classification across 2 accounts → manual transcription into 2 Excel budget sheets) with a single self-hosted app that imports transactions, classifies them (rules + on-demand AI), tracks split transactions, and produces budget views/reports — fully retiring GnuCash and the Excel sheets.

- **Users:** single user, no auth/multi-tenancy.
- **Deployment:** single Docker container, local (e.g. on Lucius), SQLite for storage.
- **Currency:** CAD only.
- **Accounting period:** calendar year, hardcoded (Jan 1 reset).

## 2. Data Model

### 2.1 Accounts
- Fields: name, account ID, type (**asset** or **liability**), opening balance.
- Running balance = opening balance + Σ transactions to date (display only — no reconciliation against bank statements).
- Sign/column convention differs by type (asset: deposit increases / debit decreases; liability: credit increases balance owed / debit-payment decreases), but budget spend recognition is always **at time of purchase**, not at time of payment.

### 2.2 Categories
- User-defined, **hierarchical** (e.g. `shared → groceries → alcohol`).
- Fully user-manageable at will: create, rename (in place, no effect on history), and **soft-delete/archive** (archived categories disappear from pickers/rule targets but remain valid on historical transactions and in historical reports).
- Users can **reorder categories** (drag-and-drop, within their sibling group — top-level order among themselves, children within their own parent). This order is the single source of truth for category display order across the app: Overview's category table, Budgets' category tree/report rows, and any category picker/filter list all follow it.
- Auto-assigned colour on creation, **hash-based/deterministic** from category ID (not sequential), user can override.
- Parent category values (budget and actual spend) are always **derived** (sum of children) — never independently set.

### 2.3 Transactions
- Sources: **QIF import** and **manual entry** (create/edit/delete) — CSV import is out of scope for v1.
- Each transaction belongs to exactly one account.
- **Splits:** a transaction can be divided across multiple categories; each category may appear **at most once** per transaction (no duplicate category splits — merge instead); split amounts must sum to the transaction total.
- **Transfers:** a distinct transaction type for moves between the user's own accounts (e.g. credit card payment). Linked pair, excluded from expense/income totals and budget rollups by construction.
- Split editing is allowed post-import.

### 2.4 Import & Deduplication
- QIF parser only.
- Duplicate detection: exact match on **(account, date, amount, normalized name/memo)** → auto-skip.
- Near-matches (same account/date/amount, differing memo — e.g. pending → posted) go to a **manual review queue**; user decides: new transaction / merge as update (overwrite memo, keep existing category & split) / skip.
- Categorization runs **automatically, asynchronously**, immediately after import completes (import response is not blocked on it).
- The file is chosen **first**; the app then previews it and asks for confirmation: the accounts it references, the existing account each one auto-matched to (by name or account number, user-overridable, or create a new account), and a per-account dry run of what will be imported / skipped as duplicate / flagged for review. Nothing is written until that is confirmed.

## 3. Categorization Engine

### 3.1 Rule Engine
- Rule = **[ANY | ALL]** of a flat list of conditions → target category. No nested AND/OR groups in v1.
- Condition fields: date (incl. day-of-month), transaction name/memo, account, amount.
- Operators: contains, does not contain, equals, less than, greater than, (and similar standard comparisons appropriate to field type).
- Rules are **user-ordered**; evaluation is **first-match-wins** (drag-reorder or explicit priority).
- Rules are user-creatable/editable directly, **and** auto-suggested:
  - After manual categorization, the app detects repeating patterns (e.g. same merchant, or merchant+amount) across history and proposes a rule once a repetition threshold is met.
  - Suggested rules surface on matching uncategorized transactions with a **dashed border / lighter shade**, plus inline **accept (✓)** / **reject (✗)** controls and a **hover tooltip** explaining the rule.
  - Editing a suggested (or any) rule opens a **modal dialog**.
  - Creating/editing a rule via the modal **immediately re-triggers categorization** against all currently-uncategorized transactions.
- Manual **"re-run categorization"** action available for a single transaction or a bulk/filtered selection (same underlying mechanism, different scope) — does not touch already-confirmed categories.

### 3.2 AI-Assisted Categorization
- **On-demand only** — never runs automatically as part of import or the rule pipeline.
- Invoked explicitly via the API (through a Claude skill/MCP adapter) against remaining uncategorized transactions.
- AI suggestions render through the **same suggestion UI** as rule-based suggestions (dashed border, accept/reject, hover explanation).

## 4. Budgets

- Budget amount is set **per category per month** (not a single flat recurring value) — supports seasonal variation (e.g. higher December budget).
- Only **leaf categories** are directly budgeted; parent categories show derived/rolled-up totals.
- **Category balance** = cumulative, with carryover: `Σ(budgeted) − Σ(actual)` from Jan 1 to current date, per category. Under-spend in one month carries forward as available balance in the next.
- **Reports:**
  - Saved, named report definitions: user-chosen list and order of categories.
  - Report layout: rows = categories (parent rows show rolled-up totals), columns = **months (Jan → current)**, each cell showing budgeted / actual / diff, plus a YTD total.
  - Date range is fixed **Jan-to-current** (no arbitrary range picker in v1).

## 5. UI / Layout

Sidebar (left) + content area (right). Shared sidebar menu: **Overview, Accounts, Transactions, Budgets, Import**. (The prototype wireframe also includes a Settings screen — API key, categories, categorization rules, backup/restore — housed under a sixth sidebar item. See `docs/wireframes.html` for the full interactive mockup.)

- **Overview:** category table (budgeted / actual / balance, YTD) following the user-configured category order (see Section 2.2); all monetary values shown with a `$` prefix; negative balances shown in red; a grand total row (Σ expense actuals − Σ income actual) at the bottom. Plus a count of uncategorized entries linking to a filtered Transactions view (no inline categorization UI on this page).
- **Accounts:** list/edit accounts (name, ID, type). Selecting an account shows its transactions from start of accounting period in **5 columns**: Date, Name, Category, Deposit/Debit, Withdraw/Credit. Split transactions render as **multiple grouped rows** (visually linked, e.g. shared border/background), one row per split.
- **Transactions:** same table as Accounts plus an **Account** column; global filter/search by **date range, amount range, name (text), category (with rollup — filtering a parent includes its children), and account**. **Server-side pagination, 100 rows/page.**
- **Budgets:** define per-category-per-month budgets; view saved reports (category list + order, per Section 4).
- **Import:** simple file input + submit button (QIF only).

## 6. API

- **REST API** covering all entities and actions (accounts, transactions, splits, categories, rules, budgets, reports, import, backup/restore) — the system of record for all app logic.
- Auth: **static API key / bearer token** (single shared secret; proportionate to single-user, trusted-network deployment with defense-in-depth).
- A separate, thin **MCP adapter** (or Claude skill) wraps the REST API for AI/skill-based access — the core app does not speak MCP natively.

## 7. Backup / Restore

- Raw SQLite **file export** (download) and **import** (restore/replace) via the app — no structured/schema-portable dump format in v1.

## 8. Non-Functional Requirements

- **Testing:** ≥90% coverage on backend/API and core logic (QIF parsing, dedupe matching, rule engine, split validation, budget rollup math). Frontend held to a lighter bar (smoke/interaction tests, not line-coverage target).
- **Deployment:** single Docker container (FastAPI serving both API routes and built React static assets), SQLite file on a mounted volume. No docker-compose/multi-service topology required.
- **Stack:** Python (FastAPI) backend, SQLite storage, React SPA frontend.

## 9. Explicitly Out of Scope (v1)

- GnuCash data migration / historical import.
- CSV import (QIF only).
- Multi-user access, authentication beyond a single static API key.
- Balance reconciliation against bank-stated statement balances.
- Multi-currency support.
- Configurable/non-calendar fiscal year.
- Nested (AND/OR) rule condition groups.
- Configurable date range for budget reports (fixed Jan–current only).
- Notifications/alerts (e.g. over-budget warnings).
- Charts/visualizations in reports (table-only for v1).
- Mobile-optimized layout.
- Investment/loan or other account types beyond asset (checking-style) and liability (credit-card-style).

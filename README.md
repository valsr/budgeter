# budgeter

Single-user, local-only personal finance tracker (Python/FastAPI + SQLite backend, React SPA frontend). See [docs/requirements.md](docs/requirements.md) for the full spec and [docs/wireframes.html](docs/wireframes.html) for a clickable UI prototype (open it directly in a browser).

## Backend setup (Python venv)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Run the dev server:

```bash
uvicorn app.main:app --reload --port 8000
```

Config is read from environment variables (prefix `BUDGETER_`) or a `backend/.env` file — see `app/config.py`. Notably `BUDGETER_API_KEY` (the bearer token the frontend/MCP clients must send) and `BUDGETER_DATABASE_URL` (defaults to a local `budgeter.db` SQLite file).

Run tests with coverage:

```bash
pytest
```

Coverage config lives in `pytest.ini` / `.coveragerc` and targets `app/`, with an emphasis on ≥90% coverage for core logic (QIF parsing, dedupe, rule engine, split validation, budget rollups).

Database migrations (Alembic):

```bash
alembic revision --autogenerate -m "message"
alembic upgrade head
```

## Frontend setup (Vite dev server)

```bash
cd frontend
npm install
npm run dev
```

Opens on http://localhost:5173 and expects the backend on http://localhost:8000 by default (override via `VITE_API_BASE_URL` / `VITE_API_KEY` env vars, e.g. in a `frontend/.env.local` file).

Build for production:

```bash
npm run build
```

Output goes to `frontend/dist/` — kept as a conventional Vite build path so a later step (FastAPI serving the built static assets from a single Docker container) can pick it up without restructuring.

Run frontend smoke/interaction tests (Vitest + React Testing Library):

```bash
npm test
```

## MCP adapter (optional)

A thin MCP server wrapping the REST API — lets Claude/skills browse accounts, transactions, and categories, and submit on-demand AI category suggestions. See [mcp_adapter/README.md](mcp_adapter/README.md) for setup and the list of tools. Runs as its own process (its own venv, no code shared with `backend/`); the core app doesn't speak MCP natively.

## Deployment

Out of scope for the current phase. The eventual plan (see `docs/requirements.md` §8) is a single Docker container running FastAPI, serving both the API and the built `frontend/dist/` static assets, backed by a SQLite file on a mounted volume. For now, run the backend and frontend dev servers side by side as described above.

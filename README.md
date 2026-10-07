# budgeter

Self-hosted personal finance tracker with per-user logins and separate books for each user (Python/FastAPI + SQLite backend, React SPA frontend). See [docs/requirements.md](docs/requirements.md) for the full spec and [docs/wireframes.html](docs/wireframes.html) for a clickable UI prototype (open it directly in a browser).

## Backend setup (Python venv)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt   # includes requirements.txt + pytest/httpx
```

(`requirements.txt` alone has just the runtime deps — that's what the container image installs.)

Run the dev server:

```bash
uvicorn app.main:app --reload --port 8000
```

Config is read from environment variables (prefix `BUDGETER_`) or a `backend/.env` file — see `app/config.py`. Notably `BUDGETER_DATA_DIR`, the directory holding `server.db` (logins) and `books/<user_id>.db` (one SQLite file of books per user). It defaults to the directory of the file `BUDGETER_DATABASE_URL` names (a local `budgeter.db` by default) — that file is the database from before user accounts existed, and the first user to register gets a copy of it as their books.

Open the app and create an account to get started: the first account on a server can always register, and every account is an admin until another admin says otherwise (Settings → Users / Server). Scripts and the MCP adapter authenticate with a per-user API key from Settings → Account.

Run tests with coverage:

```bash
pytest
```

Coverage config lives in `pytest.ini` / `.coveragerc` and targets `app/`, with an emphasis on ≥90% coverage for core logic (QIF parsing, dedupe, rule engine, split validation, budget rollups).

Database migrations (Alembic):

There are two migration trees — one for a user's books, one for the server database (users, sessions). See [CLAUDE.md](CLAUDE.md) for which is which and the exact commands; the app applies both automatically on startup.

## Frontend setup (Vite dev server)

```bash
cd frontend
npm install
npm run dev
```

Opens on http://localhost:5173 and expects the backend on http://localhost:8000 by default (override via the `VITE_API_BASE_URL` env var, e.g. in a `frontend/.env.local` file). The browser logs in with a username and password and holds a session cookie; there is no API key to configure for it.

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

## Container (Podman)

A single container runs FastAPI, serving both the API and the built frontend static assets, per `docs/requirements.md` §8. See [docs/container.md](docs/container.md) for build/run instructions — short version:

```bash
scripts/podman-build.sh
scripts/podman-run.sh
```

All data (the server database and every user's books) lives on a named volume (`budgeter-data`) mounted at `/data`, so it survives container restarts/rebuilds.

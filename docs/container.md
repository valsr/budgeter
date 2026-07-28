# Container (Podman)

Single container, per `docs/requirements.md` §8: FastAPI serves both the REST API (under `/api/*`) and the built React static assets (everything else, with client-side routing fallback to `index.html`). SQLite lives on a named volume mounted at `/data` so it survives restarts and rebuilds.

## Build

```bash
scripts/podman-build.sh
```

Equivalent to:

```bash
podman build --file Containerfile --build-arg API_KEY=dev-local-api-key --tag budgeter:latest .
```

### About the API key

The key itself lives in the database (`api_key` table), not just in config — the backend checks incoming bearer tokens against that row, falling back to `BUDGETER_API_KEY` only when the row doesn't exist yet. The frontend is a static SPA, though, so its *first* request needs a key compiled in at `npm run build` time (via `VITE_API_KEY`); the build step and the run step need to agree on that initial value:

```bash
API_KEY=my-secret scripts/podman-build.sh
API_KEY=my-secret scripts/podman-run.sh
```

If you don't pass one, both scripts default to `dev-local-api-key` (same default the dev servers use), so it works out of the box for local single-user use.

You can regenerate the key later from Settings → API key without rebuilding — the new value is stored server-side and the browser that clicked "Regenerate" keeps working automatically (it caches the new key in `localStorage`). Two things to update by hand afterwards: any other browser/device hitting this instance (it has no way to recover from a stale compiled-in key except being given the new one), and the MCP adapter's `BUDGETER_MCP_API_KEY` env var, which is a separate client and won't pick up the change on its own.

## Run

```bash
scripts/podman-run.sh
```

Equivalent to:

```bash
podman volume create budgeter-data
podman run --rm --name budgeter \
  --publish 8000:8000 \
  --env BUDGETER_API_KEY=dev-local-api-key \
  --volume budgeter-data:/data \
  budgeter:latest
```

Then open http://localhost:8000 — the API and frontend are both served from that same port.

Useful overrides (env vars on the scripts, not container env vars): `IMAGE_NAME`, `IMAGE_TAG`, `CONTAINER_NAME`, `HOST_PORT`, `VOLUME_NAME`.

## What happens at container start

`backend/entrypoint.sh` runs `alembic upgrade head` against `/data/budgeter.db` (via `BUDGETER_DATABASE_URL=sqlite:////data/budgeter.db`, baked into the image) before starting `uvicorn`, so schema migrations apply automatically on every container start — including the first one, which creates the database file on the volume.

## Backup/restore with the container

The app's own backup/restore (Settings → Backup & restore, or `GET`/`POST /api/backup*`) works the same as in dev — it operates on whatever file `BUDGETER_DATABASE_URL` points to, which inside the container is `/data/budgeter.db` on the named volume. You can also back up the volume directly:

```bash
podman volume export budgeter-data > budgeter-backup.tar
```

## Rebuilding

The image has no dev tooling (no pytest/httpx — see `backend/requirements.txt` vs `backend/requirements-dev.txt`) and no source bind-mount; code changes require a rebuild (`scripts/podman-build.sh`) and a fresh `podman run`. The data volume is untouched by rebuilds.

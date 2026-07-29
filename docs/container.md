# Container (Podman)

Single container, per `docs/requirements.md` §8: FastAPI serves both the REST API (under `/api/*`) and the built React static assets (everything else, with client-side routing fallback to `index.html`). SQLite lives on a named volume mounted at `/data` so it survives restarts and rebuilds.

## Build

```bash
scripts/podman-build.sh
```

Equivalent to:

```bash
podman build --file Containerfile --build-arg API_KEY=dev-local-api-key --tag com.valsr.budgeter:latest .
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
  com.valsr.budgeter:latest
```

Then open http://localhost:8000 — the API and frontend are both served from that same port.

Useful overrides (env vars on the scripts, not container env vars): `IMAGE_NAME`, `IMAGE_TAG`, `CONTAINER_NAME`, `HOST_PORT`, `VOLUME_NAME`.

## What happens at container start

The app migrates its own schema to head on startup (`upgrade_to_head()` in `backend/app/db.py`, run from `main.py`'s FastAPI lifespan hook, against `/data/budgeter.db` via `BUDGETER_DATABASE_URL=sqlite:////data/budgeter.db`) — no separate migration step runs in `entrypoint.sh`. This applies on every container start, including the first one, which creates the database file on the volume. See [CLAUDE.md](../CLAUDE.md) for the policy this follows.

## Backup/restore with the container

The app's own backup/restore (Settings → Backup & restore, or `GET`/`POST /api/backup*`) works the same as in dev — it operates on whatever file `BUDGETER_DATABASE_URL` points to, which inside the container is `/data/budgeter.db` on the named volume. You can also back up the volume directly:

```bash
podman volume export budgeter-data > budgeter-backup.tar
```

## Rebuilding / updating

The image has no dev tooling (no pytest/httpx — see `backend/requirements.txt` vs `backend/requirements-dev.txt`) and no source bind-mount; code changes require a rebuild and a fresh container. The data volume is untouched by rebuilds — it's named (`budgeter-data` by default) and outlives any single container, so swapping the image doesn't touch it.

There's no image registry in this setup (single self-hosted deployment) — a new image just needs to end up tagged `com.valsr.budgeter:latest` (or whatever `IMAGE_NAME`/`IMAGE_TAG` you use) on the host that runs it, however it gets there (`scripts/podman-build.sh` on that host, or a `podman load` of a tarball built elsewhere). Once it is, redeploy with:

```bash
scripts/podman-update.sh
```

This removes the currently-running `budgeter` container (if any — the data volume it was using is untouched) and starts a fresh one from the image now tagged `latest`, same as `podman-run.sh`. Equivalent to:

```bash
podman rm -f budgeter   # only if it's currently running
scripts/podman-run.sh
```

Same env var overrides as the other scripts apply (`IMAGE_NAME`, `IMAGE_TAG`, `CONTAINER_NAME`, `HOST_PORT`, `API_KEY`, `VOLUME_NAME`) — `podman-update.sh` just forwards to `podman-run.sh` for the actual `podman run`, so pass them the same way.

### Always start the container via these scripts

The Containerfile declares `VOLUME ["/data"]`, so running the image with a bare `podman run` (no `--volume` flag) still "works" — Podman silently creates a fresh **anonymous** volume to satisfy it. The app runs fine, but that volume isn't `budgeter-data`, has no name to `podman volume export` by, and nothing links it back to the container once removed. `podman-run.sh`/`podman-update.sh` always pass `--volume budgeter-data:/data` explicitly for exactly this reason — always start/update through them (or pass the same flag by hand) rather than a bare `podman run`, or you'll end up with data silently stranded in an unnamed volume next time you redeploy. `podman volume ls` shows any orphaned anonymous ones (long hex names, no container using them) if this has already happened.

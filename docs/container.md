# Container (Podman)

Single container, per `docs/requirements.md` §8: FastAPI serves both the REST API (under `/api/*`) and the built React static assets (everything else, with client-side routing fallback to `index.html`). All data lives on a named volume mounted at `/data` so it survives restarts and rebuilds:

```
/data/server.db            users, sessions, server settings
/data/books/<user_id>.db   one user's books
/data/budgeter.db          only on volumes from before user accounts: read once, never modified
```

## Build

```bash
scripts/podman-build.sh
```

Equivalent to:

```bash
podman build --file Containerfile --tag com.valsr.budgeter:latest .
```

The script stamps the image with the commit it was built from and the build time (`GIT_SHA`, `GIT_COMMIT_DATE`, `BUILD_DATE` build args; it uses `GITHUB_SHA` when run in GitHub Actions), which the app reports as its version. A bare `podman build` without those args still works; the app then reports its version as `unknown`. Commit before building, or the stamp names a commit that isn't quite what is in the image.

Nothing secret is baked into the image: the browser logs in with a username and password, and API keys are per user (Settings → Account).

## Run

```bash
scripts/podman-run.sh
```

Equivalent to:

```bash
podman volume create budgeter-data
podman run --rm --name budgeter \
  --publish 8000:8000 \
  --volume budgeter-data:/data \
  com.valsr.budgeter:latest
```

Then open http://localhost:8000 — the API and frontend are both served from that same port. On a fresh volume, create the first account from the login screen; on a volume that already holds a pre-accounts `budgeter.db`, that first account takes over its data (as a copy — the original file is left in place).

Useful overrides (env vars on the scripts, not container env vars): `IMAGE_NAME`, `IMAGE_TAG`, `CONTAINER_NAME`, `HOST_PORT`, `VOLUME_NAME`.

## Port and HTTPS

The app serves plain HTTP on port 8000 until an admin changes that in Settings → Server. Both settings are read at container start, so restart the container after saving them.

- **Port:** the container's published port must follow. If you set the port to 8443, start with `CONTAINER_PORT=8443 HOST_PORT=8443 scripts/podman-run.sh`. Alternatively pin the in-container port with `--env BUDGETER_PORT=8000`, which overrides the saved value.
- **HTTPS:** the certificate and key paths are paths *inside the container*. Mount them, e.g. `CERTS_DIR=/etc/letsencrypt/live/example.org scripts/podman-run.sh`, and enter `/certs/fullchain.pem` and `/certs/privkey.pem`. The files must be readable by uid 1000 and the key must not be passphrase-protected.
- **If the certificate goes missing** the container exits at start instead of serving plain HTTP. Put the files back, or start once with `--env BUDGETER_SSL_DISABLED=true` to get in over HTTP and fix the settings.
- **Health check:** `GET /health` returns 200 when the server is up and its database reachable, 503 otherwise — suitable for `podman run --health-cmd`. Use `https://` and the configured port once those are changed.

## What happens at container start

The app migrates its own schemas to head on startup (`main.py`'s FastAPI lifespan hook: the server database first, then every user's books file) — no separate migration step runs in `entrypoint.sh`. This applies on every container start, including the first one, which creates `/data/server.db`. A user's books file is created when their account is. See [CLAUDE.md](../CLAUDE.md) for the policy this follows.

## Backup/restore with the container

The app's own backup/restore works the same as in dev. Each user can download and restore their own books (Settings → Backup & restore, or `GET`/`POST /api/backup*`). An admin can download and restore everything at once as a zip (Settings → Server, or `GET /api/admin/backup` / `POST /api/admin/backup/restore`) — restoring that replaces every user's login and data. You can also back up the volume directly:

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

Same env var overrides as the other scripts apply (`IMAGE_NAME`, `IMAGE_TAG`, `CONTAINER_NAME`, `HOST_PORT`, `VOLUME_NAME`) — `podman-update.sh` just forwards to `podman-run.sh` for the actual `podman run`, so pass them the same way.

### Always start the container via these scripts

The Containerfile declares `VOLUME ["/data"]`, so running the image with a bare `podman run` (no `--volume` flag) still "works" — Podman silently creates a fresh **anonymous** volume to satisfy it. The app runs fine, but that volume isn't `budgeter-data`, has no name to `podman volume export` by, and nothing links it back to the container once removed. `podman-run.sh`/`podman-update.sh` always pass `--volume budgeter-data:/data` explicitly for exactly this reason — always start/update through them (or pass the same flag by hand) rather than a bare `podman run`, or you'll end up with data silently stranded in an unnamed volume next time you redeploy. `podman volume ls` shows any orphaned anonymous ones (long hex names, no container using them) if this has already happened.

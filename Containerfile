# Single-container build: FastAPI serves both the REST API and the built
# React static assets, per docs/requirements.md §8. All data (server.db and
# books/<user_id>.db) lives on a volume mounted at /data (see
# scripts/podman-run.sh).

# --- Stage 1: build the frontend ---
FROM docker.io/node:24-alpine AS frontend-build
WORKDIR /app/frontend

# The frontend is a static SPA bundled at build time, so its API base URL
# is compiled in, not runtime-configurable. Empty = same origin as the page,
# which is also what lets the session cookie flow without CORS.
ENV VITE_API_BASE_URL=""

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: backend runtime, serving the built frontend too ---
FROM docker.io/python:3.14-slim AS runtime
WORKDIR /app

RUN useradd --create-home --uid 1000 budgeter

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/alembic.ini ./alembic.ini
COPY backend/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

COPY --from=frontend-build /app/frontend/dist ./app/static

# The data directory is this file's directory (/data). The file itself is
# only read, and only on volumes that predate user accounts.
ENV BUDGETER_DATABASE_URL=sqlite:////data/budgeter.db
# Listen on all interfaces inside the container; the port and HTTPS come from
# Settings → Server (default: plain HTTP on 8000).
ENV BUDGETER_HOST=0.0.0.0
RUN mkdir -p /data && chown budgeter:budgeter /data
VOLUME ["/data"]

USER budgeter
EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]

# Single-container build: FastAPI serves both the REST API and the built
# React static assets, per docs/requirements.md §8. SQLite lives on a
# volume mounted at /data (see scripts/podman-run.sh).

# --- Stage 1: build the frontend ---
FROM docker.io/node:24-alpine AS frontend-build
WORKDIR /app/frontend

# The frontend is a static SPA bundled at build time, so its API key/base
# URL are compiled in, not runtime-configurable — see docs/container.md.
ARG API_KEY=dev-local-api-key
ENV VITE_API_KEY=${API_KEY}
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

ENV BUDGETER_DATABASE_URL=sqlite:////data/budgeter.db
RUN mkdir -p /data && chown budgeter:budgeter /data
VOLUME ["/data"]

USER budgeter
EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]

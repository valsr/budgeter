from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import books, server_db
from app.routers import (
    accounts,
    ai,
    auth,
    backup,
    budgets,
    categories,
    health,
    history,
    imports,
    overview,
    rules,
    settings,
    transactions,
)
from app.services import users as users_service
from app.services.change_log import purge_expired


@asynccontextmanager
async def lifespan(app: FastAPI):
    server_db.upgrade_to_head()
    with server_db.SessionLocal() as sdb:
        users_service.purge_expired_sessions(sdb)
        user_ids = [user.id for user in users_service.list_users(sdb)]
    books.upgrade_all(user_ids)
    for user_id in user_ids:
        with books.session_for(user_id) as db:
            purge_expired(db)
            db.commit()
    yield


app = FastAPI(title="Budgeter API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(categories.router)
app.include_router(transactions.router)
app.include_router(imports.router)
app.include_router(rules.router)
app.include_router(ai.router)
app.include_router(budgets.router)
app.include_router(backup.router)
app.include_router(overview.router)
app.include_router(settings.router)
app.include_router(history.router)

# In the packaged container, the frontend's `npm run build` output is copied
# to app/static/ (see the root Containerfile). In local dev this directory
# doesn't exist, so the SPA is served by the separate Vite dev server instead
# — this mount is a no-op unless the container's build step created it.
_STATIC_DIR = Path(__file__).parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets"), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str) -> FileResponse:
        # Client-side routing: any non-API path that isn't a real static
        # file falls back to index.html so React Router can handle it.
        candidate = _STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_STATIC_DIR / "index.html")

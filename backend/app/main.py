import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import books, server_db
from app.routers import (
    accounts,
    admin,
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


logger = logging.getLogger(__name__)

# Browser origins, other than the app's own, that may call the API with
# credentials: the Vite dev server.
ALLOWED_ORIGINS = ["http://localhost:5173"]
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    server_db.upgrade_to_head()
    with server_db.SessionLocal() as sdb:
        users_service.purge_expired_sessions(sdb)
        user_ids = [user.id for user in users_service.list_users(sdb)]
    for user_id in user_ids:
        # One user's damaged books must not stop the server starting for
        # everybody else; they can restore from a backup once it's up.
        try:
            books.upgrade_all([user_id])
            with books.session_for(user_id) as db:
                purge_expired(db)
                db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Could not prepare books for user %s; skipping", user_id)
            books.dispose(user_id)
    yield


app = FastAPI(title="Budgeter API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.middleware("http")
async def refuse_cross_origin_writes(request: Request, call_next):
    """CSRF guard. The session cookie is SameSite=Lax, which stops other
    *sites* -- but another port on the same host, or a sibling subdomain,
    is the same site, and a plain form post (including a file upload to the
    restore endpoints) needs no CORS preflight. So a state-changing request
    that names an Origin must name this app's own, or an allowed one.
    Requests with no Origin (curl, scripts, the MCP adapter) aren't browsers
    acting on a cookie, and pass.
    """
    if request.method not in _SAFE_METHODS and request.url.path.startswith("/api/"):
        origin = request.headers.get("origin")
        if (
            origin
            and origin not in ALLOWED_ORIGINS
            # Compared by host[:port] only: behind a TLS-terminating proxy
            # the app sees http while the browser says https.
            and urlsplit(origin).netloc != request.headers.get("host")
        ):
            return JSONResponse({"detail": "Cross-origin request refused"}, status_code=403)
    return await call_next(request)


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(admin.router)
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

def resolve_static_path(static_dir: Path, full_path: str) -> Path:
    """Which file to serve for a non-API path: the static file it names, or
    index.html so React Router can handle a client-side route.

    The requested path is attacker-controlled (and arrives URL-decoded, so
    "%2e%2e" is ".."). It's only served if it really resolves to a file
    inside static_dir -- otherwise "/../../data/server.db" would hand out
    the databases.
    """
    index = static_dir / "index.html"
    if not full_path:
        return index
    root = static_dir.resolve()
    candidate = (root / full_path).resolve()
    if candidate.is_relative_to(root) and candidate.is_file():
        return candidate
    return index


# In the packaged container, the frontend's `npm run build` output is copied
# to app/static/ (see the root Containerfile). In local dev this directory
# doesn't exist, so the SPA is served by the separate Vite dev server instead
# — this mount is a no-op unless the container's build step created it.
_STATIC_DIR = Path(__file__).parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets"), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str) -> FileResponse:
        return FileResponse(resolve_static_path(_STATIC_DIR, full_path))

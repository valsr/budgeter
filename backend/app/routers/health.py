from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app import runtime, server_db
from app.auth import current_user
from app.version import get_version
from app.server_models import utcnow

router = APIRouter(tags=["health"])


def uptime_seconds() -> int:
    return int((utcnow() - runtime.STARTED_AT).total_seconds())


def _check_server_db() -> None:
    with server_db.SessionLocal() as db:
        db.execute(select(1)).scalar_one()


# Public, for load balancers and container health checks: says whether the
# server can do its job, and nothing an anonymous caller could use. The
# details are at /api/admin/health (routers/admin.py), for admins.
@router.get("/health")
@router.get("/api/health")
def health() -> JSONResponse:
    try:
        _check_server_db()
        ok = True
    except Exception:  # noqa: BLE001 -- any failure means "not healthy"
        ok = False
    return JSONResponse(
        {
            "status": "ok" if ok else "error",
            "uptime_seconds": uptime_seconds(),
            "checks": {"server_db": "ok" if ok else "error"},
        },
        status_code=200 if ok else 503,
    )


# For logged-in users only: which build is running is nobody else's business
# (it tells an attacker exactly which code to look for holes in).
@router.get("/api/version", dependencies=[Depends(current_user)])
def version() -> dict:
    return get_version().as_dict()

"""Server administration: other users and server-wide settings.

Nothing here reads a user's books -- an admin manages accounts, not data.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app import books, runtime
from app.auth import require_admin
from app.config import settings as app_settings
from app.errors import ConflictError, NotFoundError, ValidationError
from app.schemas.admin import (
    AdminUserRead,
    AdminUserUpdate,
    ServerSettingsRead,
    ServerSettingsUpdate,
)
from app.schemas.auth import Credentials
from app.server_db import get_server_db
from app.server_models import ServerSettings, User
from app.services import health as health_service
from app.services import server_config
from app.services import server_backup
from app.services import users as users_service

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/users", response_model=list[AdminUserRead])
def list_users(sdb: Session = Depends(get_server_db)):
    return users_service.list_users(sdb)


@router.post("/users", response_model=AdminUserRead, status_code=201)
def create_user(payload: Credentials, sdb: Session = Depends(get_server_db)):
    """Works whether or not self-registration is open."""
    try:
        user = users_service.create_user(sdb, payload.username, payload.password)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    books.create_books(user.id)
    return user


@router.patch("/users/{user_id}", response_model=AdminUserRead)
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    admin: User = Depends(require_admin),
    sdb: Session = Depends(get_server_db),
):
    if user_id == admin.id and payload.is_admin is False:
        # Giving up admin is one click from locking yourself out of this very
        # screen; it takes another admin to do it.
        raise HTTPException(status_code=409, detail="You can't remove your own admin rights")
    try:
        return users_service.update_user(
            sdb,
            user_id,
            is_admin=payload.is_admin,
            is_disabled=payload.is_disabled,
            password=payload.password,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, sdb: Session = Depends(get_server_db)):
    try:
        users_service.delete_user(sdb, user_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    # Only once the account is gone: nothing can open these books any more.
    books.delete_books(user_id)


def _settings_read(row: ServerSettings) -> ServerSettingsRead:
    return ServerSettingsRead(
        registration_open=row.registration_open,
        port=row.port,
        ssl_enabled=row.ssl_enabled,
        ssl_certfile=row.ssl_certfile,
        ssl_keyfile=row.ssl_keyfile,
        managed=runtime.current is not None,
        restart_required=server_config.restart_required(row),
        port_override=app_settings.port,
        ssl_disabled_override=app_settings.ssl_disabled,
    )


@router.get("/settings", response_model=ServerSettingsRead)
def get_settings(sdb: Session = Depends(get_server_db)):
    return _settings_read(users_service.get_settings(sdb))


@router.patch("/settings", response_model=ServerSettingsRead)
def update_settings(payload: ServerSettingsUpdate, sdb: Session = Depends(get_server_db)):
    sent = payload.model_dump(exclude_unset=True)
    try:
        # Port and SSL first: if they're refused, nothing at all is saved.
        server_config.update(
            sdb,
            port=sent.get("port"),
            ssl_enabled=sent.get("ssl_enabled"),
            **{k: sent[k] for k in ("ssl_certfile", "ssl_keyfile") if k in sent},
        )
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if sent.get("registration_open") is not None:
        users_service.set_registration_open(sdb, sent["registration_open"])
    return _settings_read(users_service.get_settings(sdb))


@router.get("/health")
def detailed_health(sdb: Session = Depends(get_server_db)):
    """Everything the public /health leaves out: who and what is on this
    server, and whether its pieces are in working order."""
    return health_service.report(sdb)


@router.get("/backup")
def download_server_backup():
    try:
        data = server_backup.create_archive()
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{server_backup.archive_filename()}"'},
    )


@router.post("/backup/restore", status_code=204)
def restore_server_backup(file: UploadFile):
    """Replaces every user's account and books with the archive's. Sessions
    come from the archive too, so callers may need to log in again."""
    data = file.file.read()
    try:
        server_backup.restore_archive(data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

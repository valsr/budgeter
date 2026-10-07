"""Server administration: other users and server-wide settings."""

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app import runtime
from app.auth import require_admin
from app.config import settings as app_settings
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
from app.services import lifecycle, server_config
from app.services import server_backup
from app.services import users as users_service

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/users", response_model=list[AdminUserRead])
def list_users(sdb: Session = Depends(get_server_db)):
    return users_service.list_users(sdb)


@router.post("/users", response_model=AdminUserRead, status_code=201)
def create_user(payload: Credentials, sdb: Session = Depends(get_server_db)):
    """Works whether or not self-registration is open."""
    user = users_service.create_user(sdb, payload.username, payload.password)
    lifecycle.provision(sdb, user)
    return user


@router.patch("/users/{user_id}", response_model=AdminUserRead)
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    admin: User = Depends(require_admin),
    sdb: Session = Depends(get_server_db),
):
    return users_service.update_user(
        sdb,
        user_id,
        is_admin=payload.is_admin,
        is_disabled=payload.is_disabled,
        password=payload.password,
        acting_user_id=admin.id,
    )


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, sdb: Session = Depends(get_server_db)):
    lifecycle.remove(sdb, user_id)


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
    # Port and SSL first: if they're refused, nothing at all is saved.
    server_config.update(
        sdb,
        port=payload.port,
        ssl_enabled=payload.ssl_enabled,
        ssl_certfile=payload.ssl_certfile,
        ssl_keyfile=payload.ssl_keyfile,
    )
    if payload.registration_open is not None:
        users_service.set_registration_open(sdb, payload.registration_open)
    return _settings_read(users_service.get_settings(sdb))


@router.get("/health")
def detailed_health(sdb: Session = Depends(get_server_db)):
    """Everything the public /health leaves out: who and what is on this
    server, and whether its pieces are in working order."""
    return health_service.report(sdb)


@router.get("/backup")
def download_server_backup():
    data = server_backup.create_archive()
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
    server_backup.restore_archive(data)

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response

from app.auth import require_api_key
from app.config import settings
from app.db import engine
from app.errors import ValidationError
from app.services import backup as backup_service

router = APIRouter(prefix="/api/backup", tags=["backup"], dependencies=[Depends(require_api_key)])


@router.get("")
def download_backup():
    db_path = backup_service.resolve_sqlite_path(settings.database_url)
    data = backup_service.create_backup_bytes(db_path)
    filename = f"budgeter-backup-{dt.date.today().isoformat()}.db"
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/restore", status_code=204)
async def restore_backup(file: UploadFile):
    data = await file.read()
    db_path = backup_service.resolve_sqlite_path(settings.database_url)
    try:
        # Release any open connections/cached file handles before swapping
        # the file out from under them.
        engine.dispose()
        backup_service.write_backup_bytes(db_path, data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

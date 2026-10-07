import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response

from app import books
from app.auth import current_user
from app.errors import ValidationError
from app.server_models import User
from app.services import backup as backup_service

router = APIRouter(prefix="/api/backup", tags=["backup"], dependencies=[Depends(current_user)])


@router.get("")
def download_backup(user: User = Depends(current_user)):
    books.ensure_books(user.id)
    data = backup_service.create_backup_bytes(str(books.books_path(user.id)))
    filename = f"budgeter-backup-{dt.date.today().isoformat()}.db"
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/restore", status_code=204)
async def restore_backup(file: UploadFile, user: User = Depends(current_user)):
    data = await file.read()
    path = books.books_path(user.id)
    try:
        backup_service.validate_books_bytes(data)
        # Release any open connections/cached file handles before swapping
        # the file out from under them.
        books.dispose(user.id)
        backup_service.write_backup_bytes(str(path), data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    # A backup from an older version of the app: bring it up to date now
    # rather than at the next restart.
    books.upgrade(path)

import datetime as dt
import logging

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import Response

from app import books
from app.auth import current_user
from app.server_models import User
from app.services import backup as backup_service
from app.services import shared_tally

logger = logging.getLogger(__name__)

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
def restore_backup(file: UploadFile, user: User = Depends(current_user)):
    path = books.books_path(user.id)
    # Validated, migrated and checked as a copy first; the live books are untouched unless it's usable.
    staged = backup_service.stage_books(file.file.read(), path.with_suffix(".restore"))
    books.replace_books(user.id, staged)
    # The restore has happened; a tally failure mustn't turn it into an error. Tallies self-heal
    # on the member's next write or at startup.
    try:
        shared_tally.recompute_member(user.id)
    except Exception:
        logger.exception("Couldn't update shared budget tallies after restoring user %s's books", user.id)

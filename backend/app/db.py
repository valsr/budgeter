from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    """The books schema: everything in one user's books file (app/books.py).
    Users and sessions are a separate schema -- app/server_db.ServerBase."""


# Imported after Base: app.books needs it (lazily) to create in-memory test books.
from app import books  # noqa: E402
from app.auth import current_user  # noqa: E402
from app.server_models import User  # noqa: E402


def get_db(user: User = Depends(current_user)) -> Generator[Session, None, None]:
    """A session on the calling user's own books. There is no way to reach
    another user's data through it: it's a different file."""
    db = books.session_for(user.id)
    try:
        yield db
    finally:
        db.close()

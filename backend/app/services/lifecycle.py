"""An account is a user row plus that user's books file; these keep the two in step."""

from sqlalchemy.orm import Session

from app import books
from app.server_models import User
from app.services import users as users_service


def provision(sdb: Session, user: User, *, claim_legacy: bool = False) -> None:
    """Give a new user their books: the pre-accounts data for a server's very first
    self-registered user, empty books for everyone else."""
    if not (claim_legacy and books.claim_legacy_books(sdb, user)):
        books.create_books(user.id)


def remove(sdb: Session, user_id: int) -> None:
    users_service.delete_user(sdb, user_id)
    # Only once the account is gone: nothing can open these books any more.
    books.delete_books(user_id)

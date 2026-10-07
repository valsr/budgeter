"""Accounts, sessions and server settings. Every function here takes a
server-database session (app/server_db.py), never a user's books."""

import re
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import AuthError, ConflictError, NotFoundError, ValidationError
from app.security import hash_password, hash_token, new_token, verify_password
from app.server_models import ServerSettings, User, UserSession, utcnow

_USERNAME_RE = re.compile(r"[a-z0-9_.-]{3,32}")
MIN_PASSWORD_LENGTH = 8
# scrypt's cost doesn't grow with input length, but there's no reason to
# accept megabytes of "password" either.
MAX_PASSWORD_LENGTH = 256

SESSION_LIFETIME = timedelta(days=30)
# A session's expiry slides forward as it's used, but only once a day's
# worth has elapsed -- not a write on every single request.
_RENEW_WHEN_LEFT_BELOW = timedelta(days=29)

_BAD_CREDENTIALS = "Invalid username or password"
_LAST_ADMIN = "The last active admin can't be demoted, disabled or deleted"
# Verified against when the username is unknown, so a miss costs the same
# scrypt work as a wrong password and response time doesn't reveal which
# usernames exist.
_DUMMY_HASH = hash_password("no such user")


def normalize_username(raw: str) -> str:
    name = raw.strip().lower()
    if not _USERNAME_RE.fullmatch(name):
        raise ValidationError("Username must be 3–32 characters: letters, digits, '_', '.' or '-'")
    return name


def _validate_password(password: str) -> None:
    if not (MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH):
        raise ValidationError(
            f"Password must be {MIN_PASSWORD_LENGTH}–{MAX_PASSWORD_LENGTH} characters"
        )


def _find_by_username(db: Session, name: str) -> User | None:
    return db.execute(select(User).where(User.username == name)).scalar_one_or_none()


# --- accounts ----------------------------------------------------------


def has_users(db: Session) -> bool:
    return db.execute(select(User.id).limit(1)).first() is not None


def list_users(db: Session) -> list[User]:
    return list(db.execute(select(User).order_by(User.id)).scalars())


def get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError(f"User {user_id} not found")
    return user


def create_user(db: Session, username: str, password: str) -> User:
    name = normalize_username(username)
    _validate_password(password)
    taken = ConflictError("Username is already taken")
    if _find_by_username(db, name) is not None:
        raise taken
    user = User(username=name, password_hash=hash_password(password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Two registrations for one name can both pass the check above; the
        # unique constraint settles it.
        db.rollback()
        raise taken from None
    return user


def register(db: Session, username: str, password: str) -> User:
    """Self-service sign-up. Always allowed while there are no users at all,
    so a fresh (or emptied) server can't lock everyone out."""
    if not get_settings(db).registration_open and has_users(db):
        raise AuthError("Registration is closed")
    return create_user(db, username, password)


def authenticate(db: Session, username: str, password: str) -> User:
    user = _find_by_username(db, username.strip().lower())
    password_ok = verify_password(password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not password_ok or user.is_disabled:
        raise AuthError(_BAD_CREDENTIALS)
    return user


def change_password(db: Session, user: User, current: str, new: str, keep_token: str | None) -> None:
    if not verify_password(current, user.password_hash):
        raise AuthError("Current password is incorrect")
    _validate_password(new)
    user.password_hash = hash_password(new)
    delete_user_sessions(db, user.id, keep_token=keep_token)


def _is_active_admin(user: User) -> bool:
    return user.is_admin and not user.is_disabled


def _guard_last_admin(db: Session, user: User) -> None:
    """Refuse a change that takes `user` out of the set of active admins
    when they're the only one in it."""
    if not _is_active_admin(user):
        return
    active_admins = db.execute(
        select(func.count()).select_from(User).where(User.is_admin, ~User.is_disabled)
    ).scalar_one()
    if active_admins <= 1:
        raise ConflictError(_LAST_ADMIN)


def update_user(
    db: Session,
    user_id: int,
    *,
    is_admin: bool | None = None,
    is_disabled: bool | None = None,
    password: str | None = None,
) -> User:
    user = get_user(db, user_id)
    if is_admin is False or is_disabled is True:
        _guard_last_admin(db, user)
    if password is not None:
        _validate_password(password)

    if is_admin is not None:
        user.is_admin = is_admin
    if is_disabled is not None:
        user.is_disabled = is_disabled
    if password is not None:
        user.password_hash = hash_password(password)
    if is_disabled or password is not None:
        # Whoever held a session shouldn't keep it past a lock-out or a reset.
        db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.commit()
    return user


def delete_user(db: Session, user_id: int) -> None:
    """Remove the account and its sessions. The caller removes the user's
    books file (books.delete_books) -- this module never touches books."""
    user = get_user(db, user_id)
    _guard_last_admin(db, user)
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.delete(user)
    db.commit()


# --- sessions ----------------------------------------------------------


def create_session(db: Session, user: User) -> str:
    token = new_token()
    now = utcnow()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            created_at=now,
            expires_at=now + SESSION_LIFETIME,
        )
    )
    db.commit()
    return token


def resolve_session(db: Session, token: str, now: datetime | None = None) -> User | None:
    if not token:
        return None
    now = now or utcnow()
    row = db.execute(
        select(UserSession).where(UserSession.token_hash == hash_token(token))
    ).scalar_one_or_none()
    if row is None:
        return None
    if row.expires_at <= now:
        db.delete(row)
        db.commit()
        return None
    user = db.get(User, row.user_id)
    if user is None or user.is_disabled:
        return None
    if row.expires_at - now < _RENEW_WHEN_LEFT_BELOW:
        row.expires_at = now + SESSION_LIFETIME
        db.commit()
    return user


def delete_session(db: Session, token: str) -> None:
    db.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))
    db.commit()


def delete_user_sessions(db: Session, user_id: int, keep_token: str | None = None) -> None:
    stmt = delete(UserSession).where(UserSession.user_id == user_id)
    if keep_token:
        stmt = stmt.where(UserSession.token_hash != hash_token(keep_token))
    db.execute(stmt)
    db.commit()


def purge_expired_sessions(db: Session) -> None:
    db.execute(delete(UserSession).where(UserSession.expires_at <= utcnow()))
    db.commit()


# --- API keys ----------------------------------------------------------


def resolve_api_key(db: Session, key: str) -> User | None:
    if not key:
        return None
    user = db.execute(
        select(User).where(User.api_key_hash == hash_token(key))
    ).scalar_one_or_none()
    if user is None or user.is_disabled:
        return None
    return user


def regenerate_api_key(db: Session, user: User) -> str:
    """Returns the new key -- the only time it exists in the clear."""
    key = new_token()
    user.api_key_hash = hash_token(key)
    db.commit()
    return key


# --- server settings ---------------------------------------------------


def get_settings(db: Session) -> ServerSettings:
    row = db.execute(select(ServerSettings)).scalars().first()
    if row is None:
        row = ServerSettings()
        db.add(row)
        db.commit()
    return row


def set_registration_open(db: Session, value: bool) -> ServerSettings:
    row = get_settings(db)
    row.registration_open = value
    db.commit()
    return row

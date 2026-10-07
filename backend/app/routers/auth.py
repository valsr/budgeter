from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app import books
from app.auth import clear_session_cookie, current_user, set_session_cookie
from app.errors import AuthError, ConflictError, ValidationError
from app.schemas.auth import AuthStatus, Credentials, PasswordChange, UserRead
from app.server_db import get_server_db
from app.server_models import User
from app.services import users as users_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status", response_model=AuthStatus)
def auth_status(sdb: Session = Depends(get_server_db)):
    """Public: what the login screen needs to decide whether to offer sign-up."""
    return AuthStatus(
        registration_open=users_service.get_settings(sdb).registration_open,
        has_users=users_service.has_users(sdb),
    )


@router.post("/register", response_model=UserRead, status_code=201)
def register(
    payload: Credentials,
    request: Request,
    response: Response,
    sdb: Session = Depends(get_server_db),
):
    try:
        user = users_service.register(sdb, payload.username, payload.password)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except AuthError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    # A server's very first user inherits the data from before accounts
    # existed; everyone else starts with empty books.
    if not books.claim_legacy_books(sdb, user):
        books.create_books(user.id)
    set_session_cookie(response, request, users_service.create_session(sdb, user))
    return user


@router.post("/login", response_model=UserRead)
def login(
    payload: Credentials,
    request: Request,
    response: Response,
    sdb: Session = Depends(get_server_db),
):
    try:
        user = users_service.authenticate(sdb, payload.username, payload.password)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    set_session_cookie(response, request, users_service.create_session(sdb, user))
    return user


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    sdb: Session = Depends(get_server_db),
):
    if request.state.session_token:
        users_service.delete_session(sdb, request.state.session_token)
    clear_session_cookie(response)


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(current_user)):
    return user


@router.post("/password", status_code=204)
def change_password(
    payload: PasswordChange,
    request: Request,
    user: User = Depends(current_user),
    sdb: Session = Depends(get_server_db),
):
    try:
        users_service.change_password(
            sdb,
            user,
            payload.current_password,
            payload.new_password,
            keep_token=request.state.session_token,
        )
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

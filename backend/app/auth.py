from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.server_db import get_server_db
from app.server_models import User
from app.services import users as users_service

bearer_scheme = HTTPBearer(auto_error=False)

SESSION_COOKIE = "budgeter_session"


def current_user(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    sdb: Session = Depends(get_server_db),
) -> User:
    """Who is making this request: the owner of a bearer API key (the MCP adapter, scripts), or of
    the browser's session cookie."""
    # The raw session token, for handlers that need to tell "this session"
    # from the user's others (logout, password change). None under key auth.
    request.state.session_token = None
    user = None
    if credentials is not None:
        user = users_service.resolve_api_key(sdb, credentials.credentials)
    else:
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            user, renewed = users_service.resolve_session_renewing(sdb, token)
            if user is not None:
                request.state.session_token = token
                if renewed:
                    # Keep the browser's cookie in step with the server's sliding expiry, or it
                    # would lapse 30 days after login however active the user had been.
                    set_session_cookie(response, request, token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def set_session_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(users_service.SESSION_LIFETIME.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")

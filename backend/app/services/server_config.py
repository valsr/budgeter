"""The port and SSL settings an admin edits in Settings → Server, and what
the launcher (app/serve.py) makes of them at startup."""

import ssl
from pathlib import Path

from sqlalchemy.orm import Session

from app import runtime
from app.config import settings
from app.errors import DomainError, ValidationError
from app.server_models import ServerSettings
from app.services import users as users_service

_UNSET = object()


class StartupError(DomainError):
    """The saved settings can't be served with; the server must not start."""


def check_ssl_files(certfile: str | None, keyfile: str | None) -> None:
    """Raise ValidationError unless the two paths are a certificate and
    private key the server could actually start with."""
    if not certfile or not keyfile:
        raise ValidationError("SSL needs both a certificate file and a key file")
    for label, value in (("Certificate", certfile), ("Key", keyfile)):
        path = Path(value)
        if not path.is_absolute():
            # A relative path would depend on the directory the server
            # happened to be started from.
            raise ValidationError(f"{label} file must be an absolute path: {value}")
        if not path.is_file():
            raise ValidationError(f"{label} file not found: {value}")
    try:
        ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(certfile, keyfile)
    except (ssl.SSLError, OSError, ValueError) as e:
        # Unreadable, not PEM, a key that doesn't belong to the certificate,
        # or a passphrase-protected key (which a server can't unlock unattended).
        raise ValidationError(f"The certificate and key can't be used together: {e}") from e


def _clean_path(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def update(
    db: Session,
    *,
    port: int | None = None,
    ssl_enabled: bool | None = None,
    ssl_certfile: str | None | object = _UNSET,
    ssl_keyfile: str | None | object = _UNSET,
) -> ServerSettings:
    """Change only the settings given. Nothing is saved unless the result
    is something the server could start with: enabling SSL (or changing the
    files while it's on) requires a working certificate and key *now*, so
    the next restart doesn't discover the problem instead."""
    row = users_service.get_settings(db)

    new_port = row.port if port is None else port
    if not (1 <= new_port <= 65535):
        raise ValidationError("Port must be between 1 and 65535")
    new_cert = row.ssl_certfile if ssl_certfile is _UNSET else _clean_path(ssl_certfile)
    new_key = row.ssl_keyfile if ssl_keyfile is _UNSET else _clean_path(ssl_keyfile)
    new_enabled = row.ssl_enabled if ssl_enabled is None else ssl_enabled
    if new_enabled:
        check_ssl_files(new_cert, new_key)

    row.port, row.ssl_enabled, row.ssl_certfile, row.ssl_keyfile = new_port, new_enabled, new_cert, new_key
    db.commit()
    return row


def planned(row: ServerSettings) -> runtime.Runtime:
    """What the next start would serve with: the saved settings, after the
    environment overrides. Doesn't check that the SSL files are still there."""
    use_ssl = row.ssl_enabled and not settings.ssl_disabled
    return runtime.Runtime(
        port=settings.port or row.port,
        ssl_certfile=row.ssl_certfile if use_ssl else None,
        ssl_keyfile=row.ssl_keyfile if use_ssl else None,
    )


def resolve_startup(db: Session) -> runtime.Runtime:
    """What to serve with right now. Raises StartupError if SSL is enabled
    but its files can't be used: falling back to plain HTTP would quietly
    serve logins unencrypted, so the server refuses to start instead."""
    row = users_service.get_settings(db)
    plan = planned(row)
    if plan.ssl_enabled:
        try:
            check_ssl_files(plan.ssl_certfile, plan.ssl_keyfile)
        except ValidationError as e:
            raise StartupError(str(e)) from e
    return plan


def restart_required(row: ServerSettings) -> bool:
    """Whether the saved settings differ from what this process is serving."""
    return runtime.current is not None and planned(row) != runtime.current

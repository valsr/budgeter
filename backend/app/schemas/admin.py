import datetime as dt

from pydantic import BaseModel, ConfigDict


class AdminUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    is_admin: bool
    is_disabled: bool
    created_at: dt.datetime


class AdminUserUpdate(BaseModel):
    is_admin: bool | None = None
    is_disabled: bool | None = None
    password: str | None = None
    """Set to reset the user's password; ends their sessions."""


class ServerSettingsRead(BaseModel):
    registration_open: bool
    port: int
    ssl_enabled: bool
    ssl_certfile: str | None
    ssl_keyfile: str | None
    managed: bool
    """Whether this process was started by the launcher (app/serve.py) and
    so actually serves with the port and SSL settings above. False under a
    bare `uvicorn app.main:app`, where they are saved but not applied."""
    restart_required: bool
    """The saved port/SSL settings differ from what is being served."""
    port_override: int | None
    """BUDGETER_PORT, when set: it wins over `port`."""
    ssl_disabled_override: bool
    """BUDGETER_SSL_DISABLED: SSL stays off whatever `ssl_enabled` says."""


class ServerSettingsUpdate(BaseModel):
    """Every field optional: only what is sent changes."""

    registration_open: bool | None = None
    port: int | None = None
    ssl_enabled: bool | None = None
    ssl_certfile: str | None = None
    ssl_keyfile: str | None = None

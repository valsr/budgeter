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
    model_config = ConfigDict(from_attributes=True)

    registration_open: bool


class ServerSettingsUpdate(BaseModel):
    registration_open: bool

from pydantic import BaseModel, ConfigDict


class Credentials(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    is_admin: bool


class AuthStatus(BaseModel):
    registration_open: bool
    has_users: bool
    """False on a server nobody has registered on yet -- registration is
    always open then, whatever registration_open says."""


class ApiKeyStatus(BaseModel):
    has_key: bool


class ApiKeyReveal(BaseModel):
    api_key: str

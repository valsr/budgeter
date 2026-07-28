from pydantic import BaseModel


class ApiKeyRead(BaseModel):
    api_key: str

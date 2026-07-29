from pydantic import BaseModel


class RetentionSettings(BaseModel):
    retention_days: int

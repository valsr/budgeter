from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BUDGETER_", env_file=".env")

    api_key: str = "dev-local-api-key"
    database_url: str = "sqlite:///./budgeter.db"


settings = Settings()

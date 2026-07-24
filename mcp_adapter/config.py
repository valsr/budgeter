from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BUDGETER_MCP_", env_file=".env")

    api_base_url: str = "http://localhost:8000"
    api_key: str = "dev-local-api-key"


settings = Settings()

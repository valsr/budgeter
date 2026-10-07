from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BUDGETER_MCP_", env_file=".env")

    api_base_url: str = "http://localhost:8000"
    # A budgeter user's API key (Settings → Account). The adapter acts as
    # that user; there is no shared or default key any more.
    api_key: str = ""


settings = Settings()

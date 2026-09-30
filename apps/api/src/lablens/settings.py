from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LABLENS_", env_file=".env", extra="ignore")
    environment: str = "development"
    database_url: str = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/lablens"
    gateway_secret: str = "local-development-only-change-this-secret"
    pool_size: int = 5
    ai_api_key: str = ""
    ai_base_url: str = "https://api.featherless.ai/v1"
    ai_model: str = ""
    session_days: int = 30

    @model_validator(mode="after")
    def production(self):
        if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("LabLens requires PostgreSQL.")
        self.database_url = self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        if self.environment not in {"development", "test", "production"}:
            raise ValueError("Invalid environment.")
        if self.environment == "production" and (
            len(self.gateway_secret) < 48 or self.gateway_secret.startswith("local-")
        ):
            raise ValueError("Production requires a random gateway secret of at least 48 characters.")
        if not self.ai_base_url.startswith("https://") or "@" in self.ai_base_url:
            raise ValueError("AI providers must use a configured HTTPS origin.")
        return self


@lru_cache
def settings():
    return Settings()

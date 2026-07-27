from functools import lru_cache
from typing import Literal

from pydantic import AnyUrl, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated runtime configuration loaded exclusively from the environment."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")
    app_name: str = "Enterprise AI Employee API"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    database_url: AnyUrl = "sqlite+aiosqlite:///./app.db"
    redis_url: RedisDsn = "redis://localhost:6379/0"
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7


@lru_cache
def get_settings() -> Settings:
    return Settings()

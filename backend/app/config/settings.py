from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyUrl, RedisDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated runtime configuration loaded exclusively from the environment."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")
    app_name: str = "Enterprise AI Employee API"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"
    trusted_proxy_count: int = 0
    api_v1_prefix: str = "/api/v1"
    database_url: AnyUrl = "sqlite+aiosqlite:///./app.db"
    redis_url: RedisDsn = "redis://localhost:6379/0"
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    llm_provider: str = "OLLAMA"
    ollama_url: str = "http://host.docker.internal:11434"
    default_model: str = "qwen3"
    temperature: float = 0.7
    max_tokens: int = 512
    request_timeout: float = 30.0
    default_agent: str = "general"
    langgraph_debug: bool = False
    agent_timeout: float = 120.0
    memory_enabled: bool = True
    memory_recent_messages: int = 20
    memory_max_context_chars: int = 12000
    memory_redis_ttl_seconds: int = 3600
    rag_enabled: bool = True
    max_document_size_mb: int = 10
    document_storage_path: Path = Path("/app/data/documents")
    rag_chunk_size: int = 1000
    rag_chunk_overlap: int = 150
    rag_top_k: int = 5
    rag_similarity_threshold: float = 0.4
    embedding_provider: str = "ollama"
    embedding_model: str = "nomic-embed-text"
    embedding_base_url: str = "http://host.docker.internal:11434"
    embedding_timeout: float = 30.0
    multi_agent_enabled: bool = True
    max_agent_delegations: int = 4
    max_agent_steps: int = 8
    max_agent_task_length: int = 4000
    integrations_enabled: bool = True
    local_connectors_enabled: bool = True
    mcp_enabled: bool = True
    mcp_request_timeout_seconds: float = 15.0
    connector_max_result_size: int = 50_000
    workspace_connector_path: Path = Path("/app/data/workspace")
    connector_audit_enabled: bool = True
    workflow_max_retries: int = 2
    rate_limit_requests_per_minute: int = 60
    rate_limit_auth_per_minute: int = 10
    request_max_bytes: int = 1_000_000

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL is invalid")
        return normalized

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def validate_production_configuration(self) -> "Settings":
        if self.app_env == "production":
            if self.jwt_secret_key == "change-me-in-production" or len(self.jwt_secret_key) < 32:
                raise ValueError("JWT_SECRET_KEY must be a strong production secret")
            if not self.allowed_origins or "*" in self.allowed_origins:
                raise ValueError("CORS_ORIGINS must contain explicit production origins")
            if self.database_url.scheme.startswith("sqlite"):
                raise ValueError("DATABASE_URL must use PostgreSQL in production")
        if self.request_max_bytes < 1_024:
            raise ValueError("REQUEST_MAX_BYTES is too small")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

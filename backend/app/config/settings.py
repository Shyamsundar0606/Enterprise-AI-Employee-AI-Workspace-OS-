from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyUrl, RedisDsn
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


@lru_cache
def get_settings() -> Settings:
    return Settings()

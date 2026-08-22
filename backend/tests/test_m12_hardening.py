"""Focused M12 production-hardening regression tests."""

import logging

import pytest
from app.config.settings import Settings
from app.main import app
from app.utils.logging import JsonFormatter
from fastapi.testclient import TestClient


def test_production_configuration_requires_safe_jwt_and_explicit_cors() -> None:
    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        Settings(
            app_env="production",
            jwt_secret_key="change-me-in-production",
            cors_origins="https://workspace.example",
        )
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings(
            app_env="production",
            jwt_secret_key="x" * 32,
            database_url="postgresql+asyncpg://user:password@db/example",
            cors_origins="*",
        )
    settings = Settings(
        app_env="production",
        jwt_secret_key="x" * 32,
        database_url="postgresql+asyncpg://user:password@db/example",
        cors_origins="https://workspace.example",
    )
    assert settings.allowed_origins == ["https://workspace.example"]


def test_request_id_security_headers_metrics_and_safe_500() -> None:
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/health", headers={"X-Request-ID": "safe-id_123"})
        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == "safe-id_123"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        invalid = client.get("/api/v1/health", headers={"X-Request-ID": "x" * 129})
        assert invalid.status_code == 200
        assert invalid.headers["X-Request-ID"] != "x" * 129
        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert "enterprise_http_requests_total" in metrics.text


def test_rate_limit_returns_safe_429(monkeypatch: pytest.MonkeyPatch) -> None:
    async def blocked(**_kwargs) -> tuple[bool, int]:
        return False, 30

    import app.main as main_module

    monkeypatch.setattr(main_module.rate_limiter, "allow", blocked)
    with TestClient(app) as client:
        response = client.post("/api/v1/auth/login", json={"username": "any", "password": "any"})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"
    assert response.json() == {"detail": "Rate limit exceeded."}


def test_structured_logs_do_not_serialize_sensitive_extra_fields() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "safe_event", (), None)
    record.password = "do-not-log"  # type: ignore[attr-defined]
    record.authorization = "Bearer token"  # type: ignore[attr-defined]
    rendered = formatter.format(record)
    assert "do-not-log" not in rendered
    assert "Bearer token" not in rendered

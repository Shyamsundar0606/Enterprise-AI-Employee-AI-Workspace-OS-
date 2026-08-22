import logging
import re
import secrets
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from app.api.router import api_router
from app.api.routes.chat import chat_websocket_handler
from app.config.settings import get_settings
from app.database.redis import close_redis_client
from app.database.session import engine, init_db
from app.utils.logging import configure_logging
from app.utils.metrics import metrics
from app.utils.rate_limit import rate_limiter

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.db_engine = engine
    if engine.dialect.name == "sqlite":
        await init_db()
    logger.info("Application startup complete")
    try:
        yield
    finally:
        await close_redis_client()
        await engine.dispose()
        logger.info("Application shutdown complete")


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket) -> None:
    await chat_websocket_handler(websocket)


@app.middleware("http")
async def request_logging(request: Request, call_next):  # type: ignore[no-untyped-def]
    supplied_id = request.headers.get("X-Request-ID", "")
    request_id = (
        supplied_id
        if re.fullmatch(r"[A-Za-z0-9._-]{1,128}", supplied_id)
        else secrets.token_urlsafe(16)
    )
    started_at = time.perf_counter()
    if request.method in {"POST", "PUT", "PATCH"}:
        content_length = request.headers.get("content-length")
        if (
            content_length
            and content_length.isdigit()
            and int(content_length) > settings.request_max_bytes
        ):
            return JSONResponse(status_code=413, content={"detail": "Request body is too large."})
    sensitive_path = request.url.path.startswith(
        ("/api/v1/auth", "/api/v1/workflows", "/api/v1/approvals", "/api/v1/knowledge")
    )
    if sensitive_path:
        client_host = request.client.host if request.client else "unknown"
        limit = (
            settings.rate_limit_auth_per_minute
            if request.url.path.startswith("/api/v1/auth")
            else settings.rate_limit_requests_per_minute
        )
        allowed, retry_after = await rate_limiter.allow(
            key=f"{client_host}:{request.url.path.split('/', 4)[1:4]}", limit=limit
        )
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded."},
                headers={"Retry-After": str(retry_after)},
            )
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled request error", extra={"request_id": request_id})
        return JSONResponse(status_code=500, content={"detail": "Internal server error."})

    duration_ms = (time.perf_counter() - started_at) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'; base-uri 'self'"
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    metrics.record_http(response.status_code, duration_ms)
    logger.info(
        "http_request_completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 3),
        },
    )
    return response


@app.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> PlainTextResponse:
    """Low-cardinality, secret-free operational metrics."""
    return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.api.routes.chat import chat_websocket_handler
from app.config.settings import get_settings
from app.database.redis import close_redis_client
from app.database.session import engine, init_db
from app.utils.logging import configure_logging

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
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket) -> None:
    await chat_websocket_handler(websocket)


@app.middleware("http")
async def request_logging(request: Request, call_next):  # type: ignore[no-untyped-def]
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled request error", extra={"request_id": request_id})
        return JSONResponse(status_code=500, content={"detail": "Internal server error."})

    response.headers["X-Request-ID"] = request_id
    logger.info(
        "%s %s %s %.3fs",
        request.method,
        request.url.path,
        response.status_code,
        time.perf_counter() - started_at,
    )
    return response

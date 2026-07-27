import logging

from fastapi import APIRouter, HTTPException, Request, status

from app.schemas.health import HealthResponse, ReadinessResponse
from app.services.health import verify_dependencies

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    """Return process liveness without checking external dependencies."""
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadinessResponse)
async def readiness(request: Request) -> ReadinessResponse:
    """Return readiness only after database and Redis are available."""
    try:
        await verify_dependencies(request.app.state.db_engine)
    except Exception as exc:
        logger.exception("Readiness check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Required infrastructure is unavailable.",
        ) from exc
    return ReadinessResponse(status="ready")

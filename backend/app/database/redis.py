from redis.asyncio import Redis, from_url

from app.config.settings import get_settings

_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    """Return the process-wide asynchronous Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = from_url(str(get_settings().redis_url), decode_responses=True)
    return _redis_client


async def close_redis_client() -> None:
    """Close the Redis client safely, handling event loop closure gracefully."""
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except RuntimeError as e:
            # If event loop is closed, we can't await cleanup operations.
            # This commonly happens in tests when TestClient creates its own event loop.
            # Just clear the reference since the loop is shutting down anyway.
            if "Event loop is closed" in str(e) or "cannot schedule new futures" in str(e):
                pass  # Loop is already closing, skip async cleanup
            else:
                raise
        finally:
            _redis_client = None

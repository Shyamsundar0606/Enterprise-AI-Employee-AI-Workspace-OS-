"""Redis-backed, fail-open operational rate limiter."""

from __future__ import annotations

import hashlib

from redis.exceptions import RedisError

from app.database.redis import get_redis_client


class RateLimiter:
    async def allow(self, *, key: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
        digest = hashlib.sha256(key.encode()).hexdigest()
        redis_key = f"enterprise:rate-limit:{digest}"
        try:
            client = get_redis_client()
            count = await client.incr(redis_key)
            if count == 1:
                await client.expire(redis_key, window_seconds)
            return count <= limit, max(1, await client.ttl(redis_key))
        except RedisError:
            # Redis is an operational dependency, but transient limiter failure
            # must not turn a healthy authenticated application into a 500.
            return True, 0


rate_limiter = RateLimiter()

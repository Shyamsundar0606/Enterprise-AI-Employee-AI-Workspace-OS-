from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.database.redis import get_redis_client


async def verify_dependencies(engine: AsyncEngine) -> None:
    """Verify that essential infrastructure is responsive."""
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    await get_redis_client().ping()

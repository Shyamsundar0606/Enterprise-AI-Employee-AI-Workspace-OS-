from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import get_settings
from app.database.base import Base


def _build_engine() -> object:
    from sqlalchemy.ext.asyncio import AsyncEngine

    return create_async_engine(str(get_settings().database_url), pool_pre_ping=True)


engine = _build_engine()
AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Create ORM tables for local development and test runs."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated transactional SQLAlchemy session per request."""
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

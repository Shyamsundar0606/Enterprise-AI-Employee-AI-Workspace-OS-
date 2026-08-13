"""Pytest configuration and fixtures."""

import logging
from typing import Any

import pytest

logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def reset_redis_and_modules_between_tests() -> Any:
    """Reset Redis and module singletons between tests to avoid event loop conflicts."""
    yield
    # After each test, reset the Redis client to avoid event loop issues
    # This is crucial for tests that use TestClient (which runs with its own event loop)
    try:
        import app.database.redis as redis_module

        redis_module._redis_client = None
        logger.debug("Reset Redis client after test")
    except Exception as e:
        logger.debug(f"Error resetting Redis client: {e}")


@pytest.fixture
async def test_user():
    """Create and return a test user in the database."""
    from app.database.session import AsyncSessionFactory, init_db
    from app.models.user import User

    # Ensure tables are created
    await init_db()

    # Create a test user in the actual database
    session = AsyncSessionFactory()
    try:
        # Delete any existing test user to ensure clean state
        from sqlalchemy import delete

        await session.execute(delete(User).where(User.email == "test@example.com"))
        await session.commit()

        user = User(
            email="test@example.com",
            username="testuser",
            hashed_password="hashed_password_here",
            role="user",
            is_active=True,
        )
        session.add(user)
        await session.flush()
        await session.commit()
        # Get the user ID
        user_id = user.id

        # Return user with ID
        class TestUser:
            pass

        test_user_obj = TestUser()
        test_user_obj.id = user_id
        return test_user_obj
    finally:
        await session.close()

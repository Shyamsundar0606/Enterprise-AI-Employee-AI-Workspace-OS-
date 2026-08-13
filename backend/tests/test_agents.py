import importlib
import os
from pathlib import Path

import pytest
from app.agents.planner import RequestPlanner
from app.agents.router import ExecutionRouter
from app.agents.schemas import AgentChatRequest
from app.agents.state import create_initial_state
from app.llm.schemas import LLMChatResponse, LLMHealthResponse


def test_initial_state_and_plan_are_tool_free() -> None:
    state = create_initial_state(conversation_id="conversation-1", user_id=1, user_message="Hello")
    plan = RequestPlanner().create_plan("Hello")
    assert state["status"] == "pending"
    assert plan.requires_tools is False
    assert ExecutionRouter().select(plan) == "none"


def test_initial_state_includes_conversation_history() -> None:
    """Test that initial state can include conversation history."""
    history = [
        {"role": "user", "content": "Previous question"},
        {"role": "assistant", "content": "Previous answer"},
    ]
    state = create_initial_state(
        conversation_id="conversation-1",
        user_id=1,
        user_message="Follow up question",
        conversation_history=history,
    )
    assert state["status"] == "pending"
    assert state["conversation_history"] == history
    assert state["user_message"] == "Follow up question"


@pytest.mark.asyncio
async def test_runtime_uses_injected_llm_service(tmp_path: Path) -> None:
    """The runtime persists only for a real user in its configured database."""
    db_path = tmp_path / "agent-runtime-test.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"
    os.environ["JWT_SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256"

    import app.agents.runtime as runtime_module
    import app.config.settings as settings_module
    import app.database.session as session_module
    from app.models.user import User

    settings_module.get_settings.cache_clear()
    importlib.reload(session_module)
    importlib.reload(runtime_module)
    await session_module.init_db()

    async with session_module.AsyncSessionFactory() as session:
        user = User(
            email="agent-runtime@example.com",
            username="agentruntime",
            hashed_password="not-used-by-this-test",
            role="user",
            is_active=True,
        )
        session.add(user)
        await session.flush()
        user_id = user.id
        await session.commit()

    class FakeLLMService:
        async def chat(self, request):
            return LLMChatResponse(
                conversation_id=request.conversation_id,
                response="Hello",
                provider="fake",
                model="fake",
            )

        async def stream(self, request):
            yield {"chunk": "Hello"}

        async def health(self):
            return LLMHealthResponse(provider="fake", model="fake", status="ok")

    # Run the agent with the created user
    runtime = runtime_module.AgentRuntime(llm_service=FakeLLMService())
    request = AgentChatRequest(conversation_id="conversation-1", message="Hi")
    response = await runtime.run(user_id=user_id, request=request)
    assert response.response == "Hello"
    assert response.plan.requires_tools is False
    chunks = [chunk async for chunk in runtime.stream(user_id=user_id, request=request)]
    assert chunks == ["Hello"]

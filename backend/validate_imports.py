"""Quick validation that all new modules can be imported."""

import sys

try:
    print("Testing imports...")

    from app.config.settings import Settings, get_settings

    print("✓ Settings")

    from app.services.memory import MemoryService

    print("✓ MemoryService")

    from app.agents.context import ContextBuilder

    print("✓ ContextBuilder")

    from app.agents.state import AgentState, create_initial_state

    print("✓ AgentState")

    from app.agents.runtime import AgentRuntime

    print("✓ AgentRuntime")

    from app.api.routes.memory import router as memory_router

    print("✓ Memory routes")

    from app.api.router import api_router

    print("✓ API router")

    print("\n✅ All imports successful!")

    validated_symbols = (
        Settings,
        get_settings,
        MemoryService,
        ContextBuilder,
        AgentState,
        create_initial_state,
        AgentRuntime,
        memory_router,
        api_router,
    )
    assert all(validated_symbols)

    # Quick validation of Settings
    settings = get_settings()
    assert settings.memory_enabled is True
    assert settings.memory_recent_messages == 20
    assert settings.memory_max_context_chars == 12000
    print("✓ Settings configured correctly")

    # Quick validation of ContextBuilder
    cb = ContextBuilder()
    messages = cb.build_agent_messages(history=[], user_message="test")
    assert len(messages) == 1
    assert messages[0]["content"] == "test"
    print("✓ ContextBuilder works")

    print("\n✅ All validations passed!")
    sys.exit(0)

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator

from app.agents.context import ContextBuilder
from app.agents.graph import build_graph
from app.agents.schemas import AgentChatRequest, AgentChatResponse, AgentHealthResponse, AgentPlan
from app.agents.state import create_initial_state
from app.config.settings import get_settings
from app.database.session import AsyncSessionFactory
from app.llm.schemas import LLMChatRequest
from app.llm.service import LLMService
from app.models.user import UserRole
from app.schemas.knowledge import KnowledgeSource
from app.services.knowledge import KnowledgeError, KnowledgeService
from app.services.memory import MemoryService
from app.tools.schemas import ToolResult

logger = logging.getLogger(__name__)


class AgentRuntime:
    """Runs the LangGraph GeneralAssistant through the existing LLM abstraction."""

    def __init__(self, llm_service: LLMService | None = None) -> None:
        self._llm_service = llm_service or LLMService()
        self._settings = get_settings()
        self._context_builder = ContextBuilder()

    async def run(
        self, *, user_id: int, request: AgentChatRequest, user_role: str = UserRole.USER.value
    ) -> AgentChatResponse:
        """Run the agent with memory integration."""
        started = time.perf_counter()

        # Get a database session for memory operations
        async with AsyncSessionFactory() as session:
            memory_service = MemoryService(session)

            # Get or create conversation
            await memory_service.get_or_create_conversation(
                conversation_id=request.conversation_id, user_id=user_id
            )

            # Load conversation history
            history = await memory_service.get_recent_messages(
                conversation_id=request.conversation_id, user_id=user_id
            )

            # Build agent messages with context
            agent_messages = self._context_builder.build_agent_messages(
                history=history, user_message=request.message
            )

            retrieved_results = []
            if self._settings.rag_enabled:
                try:
                    retrieved_results = await KnowledgeService(session).search(
                        user_id=user_id,
                        query=request.message,
                    )
                except KnowledgeError:
                    logger.warning(
                        "Knowledge retrieval unavailable; continuing without document context",
                        extra={"conversation_id": request.conversation_id, "user_id": user_id},
                    )

            sources = [result.source for result in retrieved_results]
            retrieved_context = [
                {"content": result.content, "source": result.source.model_dump(mode="json")}
                for result in retrieved_results
            ]

            # Create initial state with conversation history
            state = create_initial_state(
                conversation_id=request.conversation_id,
                user_id=user_id,
                user_message=request.message,
                conversation_history=history,
                retrieved_context=retrieved_context,
                sources=[source.model_dump(mode="json") for source in sources],
            )
            state["messages"] = agent_messages
            state["user_role"] = user_role

            try:
                result = await asyncio.wait_for(
                    build_graph(self._llm_service).ainvoke(state),
                    timeout=self._settings.agent_timeout,
                )
            except Exception:
                logger.exception(
                    "Agent graph failed",
                    extra={"conversation_id": request.conversation_id},
                )
                raise

            # Persist user message
            await memory_service.save_message(
                conversation_id=request.conversation_id,
                user_id=user_id,
                role="user",
                content=request.message,
                metadata=None,
                token_count=None,
            )

            tool_result = (
                ToolResult.model_validate(result["tool_result"])
                if result.get("tool_result") is not None
                else None
            )
            if tool_result is not None:
                tool_metadata = tool_result.model_dump(mode="json")
                await memory_service.save_message(
                    conversation_id=request.conversation_id,
                    user_id=user_id,
                    role="tool",
                    content=json.dumps(
                        (
                            tool_result.output
                            if tool_result.status == "success"
                            else tool_result.error.model_dump()
                        ),
                        sort_keys=True,
                    ),
                    metadata={"tool_call": tool_metadata},
                    token_count=None,
                )

            # Persist assistant response
            assistant_response = result.get("llm_response", "")
            await memory_service.save_message(
                conversation_id=request.conversation_id,
                user_id=user_id,
                role="assistant",
                content=assistant_response,
                metadata=result.get("metadata", {}),
                token_count=None,
            )

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "Agent graph completed",
            extra={
                "conversation_id": request.conversation_id,
                "duration_ms": duration_ms,
                "provider": result.get("metadata", {}).get("provider"),
            },
        )
        return AgentChatResponse(
            conversation_id=request.conversation_id,
            response=result["llm_response"],
            plan=AgentPlan.model_validate(result["plan"]),
            provider=result.get("metadata", {}).get("provider", "unknown"),
            status=result["status"],
            duration_ms=duration_ms,
            tool_result=tool_result,
            sources=[
                KnowledgeSource.model_validate(source) for source in result.get("sources", [])
            ],
            agents_used=result.get("metadata", {}).get("agents_used", []),
            delegation_count=result.get("metadata", {}).get("delegation_count", 0),
        )

    async def stream(self, *, user_id: int, request: AgentChatRequest) -> AsyncIterator[str]:
        """Stream response from LLM (without memory integration for now)."""
        # Get a database session
        async with AsyncSessionFactory() as session:
            memory_service = MemoryService(session)

            # Ensure conversation exists
            await memory_service.get_or_create_conversation(
                conversation_id=request.conversation_id, user_id=user_id
            )

            # For streaming, we yield the LLM chunks
            # Message persistence happens separately via save_streaming_message
            async for chunk in self._llm_service.stream(
                LLMChatRequest(conversation_id=request.conversation_id, message=request.message)
            ):
                yield str(chunk["chunk"])

    async def health(self) -> AgentHealthResponse:
        """Check agent and LLM provider health."""
        provider_health = await self._llm_service.health()
        return AgentHealthResponse(
            status=provider_health.status,
            agent=self._settings.default_agent,
            provider=provider_health.provider,
            detail=provider_health.detail,
        )

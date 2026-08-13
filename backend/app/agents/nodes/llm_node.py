from datetime import UTC, datetime

from app.agents.state import AgentState
from app.llm.schemas import LLMChatRequest
from app.llm.service import LLMService


async def llm_node(state: AgentState, llm_service: LLMService) -> AgentState:
    result = await llm_service.chat(
        LLMChatRequest(conversation_id=state["conversation_id"], message=state["user_message"])
    )
    return {
        "llm_response": result.response,
        "status": "completed",
        "completed_at": datetime.now(UTC).isoformat(),
        "metadata": {"provider": result.provider},
    }

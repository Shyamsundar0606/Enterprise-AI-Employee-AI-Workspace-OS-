from datetime import UTC, datetime

from app.agents.state import AgentState
from app.llm.schemas import LLMChatRequest
from app.llm.service import LLMService


async def llm_node(state: AgentState, llm_service: LLMService) -> AgentState:
    message = state["user_message"]
    if retrieved_context := state.get("retrieved_context"):
        message = (
            f"User request: {state['user_message']}\n\n"
            "Use only the following retrieved document evidence for document-specific claims. "
            "If the evidence does not answer the request, say the available documents do not provide "
            "enough information. Do not invent facts.\n\n"
            f"Retrieved evidence: {retrieved_context}"
        )
    if tool_result := state.get("tool_result"):
        message = (
            f"User request: {state['user_message']}\n\n"
            f"Retrieved document evidence: {state.get('retrieved_context', [])}\n\n"
            f"A controlled tool has completed with this structured result: {tool_result}.\n"
            "Use only the evidence and tool result to provide a concise, natural-language answer. "
            "Do not claim a failed tool succeeded or invent unsupported document facts."
        )
    result = await llm_service.chat(
        LLMChatRequest(conversation_id=state["conversation_id"], message=message)
    )
    return {
        "llm_response": result.response,
        "status": "completed",
        "completed_at": datetime.now(UTC).isoformat(),
        "metadata": {
            "provider": result.provider,
            "tool": state.get("tool_result"),
            "sources": state.get("sources", []),
        },
    }

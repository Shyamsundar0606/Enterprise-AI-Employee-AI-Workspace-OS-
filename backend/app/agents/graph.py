"""LangGraph construction for the GeneralAssistant runtime."""

from langgraph.graph import END, START, StateGraph

from app.agents.executor import ExecutionExecutor
from app.agents.nodes.executor_node import executor_node
from app.agents.nodes.llm_node import llm_node
from app.agents.nodes.planner_node import planner_node
from app.agents.nodes.router_node import router_node
from app.agents.planner import RequestPlanner
from app.agents.router import ExecutionRouter
from app.agents.state import AgentState
from app.llm.service import LLMService


def build_graph(llm_service: LLMService):
    """Build a dependency-injected, single-agent graph."""
    graph = StateGraph(AgentState)
    planner = RequestPlanner()
    router = ExecutionRouter()
    executor = ExecutionExecutor()

    async def run_planner(state: AgentState) -> AgentState:
        return await planner_node(state, planner)

    async def run_router(state: AgentState) -> AgentState:
        return await router_node(state, router)

    async def run_executor(state: AgentState) -> AgentState:
        return await executor_node(state, executor)

    async def run_llm(state: AgentState) -> AgentState:
        return await llm_node(state, llm_service)

    graph.add_node("planner", run_planner)
    graph.add_node("router", run_router)
    graph.add_node("executor", run_executor)
    graph.add_node("llm", run_llm)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "router")
    graph.add_edge("router", "executor")
    graph.add_edge("executor", "llm")
    graph.add_edge("llm", END)
    return graph.compile()

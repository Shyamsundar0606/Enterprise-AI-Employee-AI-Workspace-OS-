"""LangGraph construction for the GeneralAssistant runtime."""

from langgraph.graph import END, START, StateGraph

from app.agents.executor import ExecutionExecutor
from app.agents.nodes.executor_node import executor_node
from app.agents.nodes.integration_node import integration_node
from app.agents.nodes.llm_node import llm_node
from app.agents.nodes.planner_node import planner_node
from app.agents.nodes.router_node import router_node
from app.agents.nodes.supervisor_node import supervisor_node
from app.agents.planner import RequestPlanner
from app.agents.router import ExecutionRouter
from app.agents.state import AgentState
from app.agents.supervisor import Supervisor
from app.integrations.executor import ConnectorExecutor
from app.integrations.router import IntegrationRouter
from app.llm.service import LLMService


def build_graph(llm_service: LLMService):
    """Build the bounded supervisor graph over the existing agent runtime."""
    graph = StateGraph(AgentState)
    planner = RequestPlanner()
    router = ExecutionRouter()
    executor = ExecutionExecutor()
    supervisor = Supervisor()
    integration_router = IntegrationRouter()
    connector_executor = ConnectorExecutor()

    async def run_supervisor(state: AgentState) -> AgentState:
        return await supervisor_node(state, supervisor)

    async def run_planner(state: AgentState) -> AgentState:
        return await planner_node(state, planner)

    async def run_integration(state: AgentState) -> AgentState:
        return await integration_node(state, integration_router, connector_executor)

    async def run_router(state: AgentState) -> AgentState:
        return await router_node(state, router)

    async def run_executor(state: AgentState) -> AgentState:
        return await executor_node(state, executor)

    async def run_llm(state: AgentState) -> AgentState:
        return await llm_node(state, llm_service)

    graph.add_node("supervisor", run_supervisor)
    graph.add_node("planner", run_planner)
    graph.add_node("integration", run_integration)
    graph.add_node("router", run_router)
    graph.add_node("executor", run_executor)
    graph.add_node("llm", run_llm)
    graph.add_edge(START, "supervisor")
    graph.add_edge("supervisor", "integration")
    graph.add_edge("integration", "planner")
    graph.add_edge("planner", "router")
    graph.add_edge("router", "executor")
    graph.add_edge("executor", "llm")
    graph.add_edge("llm", END)
    return graph.compile()

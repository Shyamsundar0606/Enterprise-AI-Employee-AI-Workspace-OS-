from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    name: str
    description: str
    capabilities: tuple[str, ...]
    allowed_tools: frozenset[str]
    requires_knowledge: bool = False
    allowed_roles: frozenset[str] = frozenset({"user", "admin"})
    enabled: bool = True


class AgentRegistry:
    """Extensible registry for runtime agent definitions."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentDefinition] = {}
        for agent in self._defaults():
            self.register(agent)

    def register(self, agent: AgentDefinition) -> None:
        if agent.name in self._agents:
            raise ValueError(f"Agent is already registered: {agent.name}")
        self._agents[agent.name] = agent

    def get(self, name: str) -> AgentDefinition:
        try:
            return self._agents[name]
        except KeyError as exc:
            raise ValueError("Requested agent is not available") from exc

    def list(self) -> list[AgentDefinition]:
        return list(self._agents.values())

    @staticmethod
    def _defaults() -> tuple[AgentDefinition, ...]:
        return (
            AgentDefinition(
                name="general",
                description="General conversation with bounded memory and safe utility tools.",
                capabilities=("conversation", "memory", "safe_tools"),
                allowed_tools=frozenset({"calculator", "current_time"}),
            ),
            AgentDefinition(
                name="knowledge",
                description="Grounded answers over the authenticated user's uploaded documents.",
                capabilities=("knowledge_retrieval", "grounded_answers", "sources"),
                allowed_tools=frozenset(),
                requires_knowledge=True,
            ),
            AgentDefinition(
                name="data",
                description="Structured numeric reasoning through the restricted calculator.",
                capabilities=("calculation", "numeric_reasoning"),
                allowed_tools=frozenset({"calculator"}),
            ),
            AgentDefinition(
                name="planner",
                description="Bounded planning and safe specialist delegation.",
                capabilities=("planning", "delegation"),
                allowed_tools=frozenset(),
            ),
            AgentDefinition(
                name="integration",
                description="Controlled enterprise connector discovery and read operations.",
                capabilities=("connector_reads", "mcp_discovery", "safe_external_data"),
                allowed_tools=frozenset(),
            ),
        )

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    name: str
    description: str


class AgentRegistry:
    """Extensible registry for runtime agent definitions."""

    def __init__(self) -> None:
        self._agents = {"general": AgentDefinition("general", "GeneralAssistant")}

    def get(self, name: str) -> AgentDefinition:
        return self._agents[name]

    def list(self) -> list[AgentDefinition]:
        return list(self._agents.values())

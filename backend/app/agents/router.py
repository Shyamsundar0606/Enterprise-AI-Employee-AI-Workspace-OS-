from app.agents.schemas import AgentPlan


class ExecutionRouter:
    """Centralizes future execution routing decisions."""

    def select(self, plan: AgentPlan) -> str:
        del plan
        return "none"

from app.agents.schemas import AgentPlan


class RequestPlanner:
    """Produces a deterministic, tool-free plan for the initial runtime."""

    def create_plan(self, user_message: str) -> AgentPlan:
        return AgentPlan(
            goal="Answer user request",
            steps=["Understand request", "Generate response"],
            requires_tools=False,
        )

from app.agents.schemas import AgentPlan


class ExecutionRouter:
    """Routes only the tool selected by the validated plan."""

    def select(self, plan: AgentPlan) -> str:
        return plan.tool_name if plan.requires_tools and plan.tool_name else "none"

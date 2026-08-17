from __future__ import annotations

import re

from app.agents.schemas import AgentPlan


class RequestPlanner:
    """Produces a narrow, deterministic plan for the allow-listed utility tools."""

    def create_plan(
        self, user_message: str, retrieved_context: list[dict[str, object]] | None = None
    ) -> AgentPlan:
        contextual_expression = self._contextual_percentage_expression(user_message, retrieved_context)
        if contextual_expression is not None:
            return AgentPlan(
                goal="Calculate a percentage using retrieved document evidence",
                steps=["Use retrieved evidence", "Validate arithmetic", "Run calculator", "Explain result"],
                requires_tools=True,
                tool_name="calculator",
                tool_input={"expression": contextual_expression},
            )

        calculator_expression = self._calculator_expression(user_message)
        if calculator_expression is not None:
            return AgentPlan(
                goal="Calculate the requested expression",
                steps=["Validate arithmetic expression", "Run calculator", "Explain result"],
                requires_tools=True,
                tool_name="calculator",
                tool_input={"expression": calculator_expression},
            )

        if re.search(
            r"\b(what(?:'s| is) the time|what time is it|current time)\b", user_message, re.I
        ):
            return AgentPlan(
                goal="Return the current time",
                steps=["Resolve requested timezone", "Run current-time tool", "Explain result"],
                requires_tools=True,
                tool_name="current_time",
                tool_input={"timezone": self._requested_timezone(user_message)},
            )

        return AgentPlan(
            goal="Answer user request",
            steps=["Understand request", "Generate response"],
            requires_tools=False,
        )

    @staticmethod
    def _calculator_expression(user_message: str) -> str | None:
        match = re.search(r"\bcalculate\s*:?[\s]*(.+)", user_message, re.I | re.S)
        return match.group(1).strip() if match and match.group(1).strip() else None

    @staticmethod
    def _requested_timezone(user_message: str) -> str:
        match = re.search(r"\bin\s+([A-Za-z_+\-/]+)", user_message)
        return match.group(1) if match else "UTC"

    @staticmethod
    def _contextual_percentage_expression(
        user_message: str, retrieved_context: list[dict[str, object]] | None
    ) -> str | None:
        percentage = re.search(r"\b(\d+(?:\.\d+)?)%\s+of\s+(?:that|it|the budget)\b", user_message, re.I)
        if percentage is None or not retrieved_context:
            return None
        content = " ".join(
            str(item.get("content", "")) for item in retrieved_context if isinstance(item, dict)
        )
        amount = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:euros?|€)\b", content, re.I)
        if amount is None:
            return None
        return f"{amount.group(1)} * {percentage.group(1)} / 100"

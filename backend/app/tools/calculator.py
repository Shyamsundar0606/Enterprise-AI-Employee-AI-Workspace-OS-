"""A deliberately restricted arithmetic calculator."""

from __future__ import annotations

import ast
import math
import operator

from pydantic import BaseModel, Field

from app.tools.base import BaseTool
from app.tools.exceptions import ToolExecutionError
from app.tools.schemas import ToolContext


class CalculatorInput(BaseModel):
    expression: str = Field(min_length=1, max_length=256)


class CalculatorOutput(BaseModel):
    result: int | float


class CalculatorTool(BaseTool):
    """Evaluate arithmetic AST nodes only; names, calls, and attributes are rejected."""

    name = "calculator"
    description = "Safely calculate a basic arithmetic expression."
    input_model = CalculatorInput
    output_model = CalculatorOutput

    async def execute(
        self, *, context: ToolContext, input_data: CalculatorInput
    ) -> CalculatorOutput:
        del context
        try:
            expression = ast.parse(input_data.expression, mode="eval")
            result = self._evaluate(expression.body)
        except (SyntaxError, ValueError, ZeroDivisionError, OverflowError) as exc:
            raise ToolExecutionError("Expression is not a permitted arithmetic expression") from exc

        if not math.isfinite(float(result)):
            raise ToolExecutionError("Expression result must be finite")
        return CalculatorOutput(result=result)

    def _evaluate(self, node: ast.expr) -> int | float:
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            if isinstance(node.value, bool):
                raise ValueError("Booleans are not valid calculator values")
            return node.value

        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd | ast.USub):
            value = self._evaluate(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value

        if isinstance(node, ast.BinOp):
            left = self._evaluate(node.left)
            right = self._evaluate(node.right)
            operations = {
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.Mult: operator.mul,
                ast.Div: operator.truediv,
                ast.FloorDiv: operator.floordiv,
                ast.Mod: operator.mod,
                ast.Pow: operator.pow,
            }
            operation = operations.get(type(node.op))
            if operation is None:
                raise ValueError("Operator is not permitted")
            if isinstance(node.op, ast.Pow) and (abs(right) > 10 or abs(left) > 1_000_000):
                raise ValueError("Exponent is outside the permitted range")
            return operation(left, right)

        raise ValueError("Only arithmetic literals and operators are permitted")

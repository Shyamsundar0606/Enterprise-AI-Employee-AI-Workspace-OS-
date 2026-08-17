"""Local current-time tool with no external dependencies."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field

from app.tools.base import BaseTool
from app.tools.exceptions import ToolExecutionError
from app.tools.schemas import ToolContext


class CurrentTimeInput(BaseModel):
    timezone: str = Field(default="UTC", min_length=1, max_length=64)


class CurrentTimeOutput(BaseModel):
    datetime: str
    timezone: str
    utc_offset: str


class CurrentTimeTool(BaseTool):
    name = "current_time"
    description = "Return the current date and time in an IANA timezone, defaulting to UTC."
    input_model = CurrentTimeInput
    output_model = CurrentTimeOutput

    async def execute(
        self, *, context: ToolContext, input_data: CurrentTimeInput
    ) -> CurrentTimeOutput:
        del context
        try:
            timezone = ZoneInfo(input_data.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ToolExecutionError("Timezone must be a valid IANA timezone") from exc

        current = datetime.now(timezone)
        return CurrentTimeOutput(
            datetime=current.isoformat(),
            timezone=input_data.timezone,
            utc_offset=current.strftime("%z"),
        )

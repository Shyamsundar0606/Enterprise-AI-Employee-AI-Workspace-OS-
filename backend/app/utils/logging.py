import json
import logging
import sys


class JsonFormatter(logging.Formatter):
    """Minimal structured logs containing only operational-safe fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key in (
            "request_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "workflow_id",
            "conversation_id",
            "connector_id",
            "tool_name",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging(log_level: str) -> None:
    """Configure predictable process-wide console logging."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=log_level.upper(), handlers=[handler], force=True)

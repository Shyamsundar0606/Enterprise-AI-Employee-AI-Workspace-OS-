"""Redaction for untrusted connector inputs, outputs, and audit metadata."""

from __future__ import annotations

from typing import Any

_SENSITIVE = (
    "password",
    "token",
    "authorization",
    "api_key",
    "secret",
    "client_secret",
    "system_prompt",
    "chain_of_thought",
    "hidden_reasoning",
)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if any(
                    word in key.lower().replace("-", "_").replace(" ", "_") for word in _SENSITIVE
                )
                else redact(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def limit_result(value: Any, maximum: int) -> Any:
    """Bound serialised output without turning external data into instructions."""
    safe = redact(value)
    rendered = str(safe)
    if len(rendered) <= maximum:
        return safe
    return {"truncated": True, "preview": rendered[:maximum]}

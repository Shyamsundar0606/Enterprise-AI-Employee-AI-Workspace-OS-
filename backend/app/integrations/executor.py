"""Policy-enforced execution gateway for all connector calls."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.integrations.exceptions import ConnectorAuthorizationError, ConnectorError, ConnectorOperationError
from app.integrations.policy import ConnectorPolicy
from app.integrations.redaction import limit_result, redact
from app.integrations.registry import ConnectorRegistry, get_connector_registry
from app.integrations.schemas import ConnectorContext, ConnectorErrorDetail, ConnectorResult
from app.models.integration_audit import IntegrationAuditEvent

logger = logging.getLogger(__name__)


class ConnectorExecutor:
    def __init__(self, registry: ConnectorRegistry | None = None, session: AsyncSession | None = None) -> None:
        self._registry = registry or get_connector_registry()
        self._session = session
        self._settings = get_settings()

    async def execute(self, *, connector_id: str, operation: str, raw_arguments: dict[str, Any], context: ConnectorContext) -> ConnectorResult:
        safe_input = redact(raw_arguments)
        try:
            connector = self._registry.get(connector_id)
            capability = next((item for item in connector.capabilities if item.name == operation), None)
            if capability is None:
                raise ConnectorOperationError("Connector operation is not available")
            if not ConnectorPolicy.authorize(capability=capability, role=context.role, allowed_roles=connector.allowed_roles):
                raise ConnectorAuthorizationError("You are not authorized to use this connector")
            input_data = connector.input_model(operation).model_validate(raw_arguments)
        except ValidationError:
            result = self._error(connector_id, operation, "connector_input_invalid", "Connector input is invalid")
            await self._audit(result, context, safe_input)
            return result
        except ConnectorError as exc:
            result = self._error(connector_id, operation, exc.code, str(exc))
            await self._audit(result, context, safe_input)
            return result
        if ConnectorPolicy.requires_approval(capability):
            result = ConnectorResult(connector_id=connector_id, operation=operation, status="approval_required", metadata={"access_type": capability.access_type.value, "summary": f"{connector.name}: {operation}"}, requires_approval=True)
            await self._audit(result, context, safe_input)
            return result
        try:
            data = limit_result(await connector.execute(operation=operation, input_data=input_data, context=context), self._settings.connector_max_result_size)
            result = ConnectorResult(connector_id=connector_id, operation=operation, status="success", data=data, metadata={"access_type": capability.access_type.value})
        except ConnectorError as exc:
            result = self._error(connector_id, operation, exc.code, str(exc))
        except Exception:
            logger.exception("Connector execution failed", extra={"connector_id": connector_id, "operation": operation})
            result = self._error(connector_id, operation, "connector_execution_failed", "Connector execution failed safely")
        await self._audit(result, context, safe_input)
        return result

    @staticmethod
    def _error(connector_id: str, operation: str, code: str, message: str) -> ConnectorResult:
        return ConnectorResult(connector_id=connector_id, operation=operation, status="error", error=ConnectorErrorDetail(code=code, message=message))

    async def _audit(self, result: ConnectorResult, context: ConnectorContext, input_data: dict[str, Any]) -> None:
        if not self._settings.connector_audit_enabled or self._session is None:
            return
        self._session.add(IntegrationAuditEvent(user_id=context.authenticated_user_id, connector_id=result.connector_id, operation=result.operation, access_type=result.metadata.get("access_type", "unknown"), status=result.status, approval_required=result.requires_approval, request_id=context.request_id, safe_metadata={"input": input_data, "metadata": redact(result.metadata)}))
        await self._session.flush()

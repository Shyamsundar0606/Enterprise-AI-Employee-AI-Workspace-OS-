"""Explicit policy decisions for connector capabilities."""

from app.integrations.schemas import AccessType, ConnectorCapability


class ConnectorPolicy:
    """Read capabilities are automatic; consequential operations wait for approval."""

    @staticmethod
    def authorize(*, capability: ConnectorCapability, role: str, allowed_roles: frozenset[str]) -> bool:
        return role in allowed_roles

    @staticmethod
    def requires_approval(capability: ConnectorCapability) -> bool:
        return capability.access_type in {AccessType.WRITE, AccessType.DESTRUCTIVE}

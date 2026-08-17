"""Safe integration-domain errors."""


class ConnectorError(Exception):
    code = "connector_error"


class ConnectorNotFoundError(ConnectorError):
    code = "connector_not_found"


class ConnectorAuthorizationError(ConnectorError):
    code = "connector_not_authorized"


class ConnectorOperationError(ConnectorError):
    code = "connector_operation_invalid"

class LLMError(Exception):
    """Base exception for LLM provider failures."""


class ProviderConfigurationError(LLMError):
    """Raised when a provider is misconfigured."""


class ProviderUnavailableError(LLMError):
    """Raised when a provider cannot be reached."""


class ProviderAuthError(LLMError):
    """Raised when provider credentials are missing or invalid."""

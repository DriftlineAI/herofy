"""
OAuth-specific exceptions.
"""

from typing import Any

from core.errors import HerofyError


class OAuthError(HerofyError):
    """Base class for OAuth errors."""

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        error_details = details or {}
        if provider:
            error_details["provider"] = provider
        super().__init__(message=message, code="OAUTH_ERROR", details=error_details)
        self.provider = provider


class OAuthStateError(OAuthError):
    """State parameter invalid, expired, or already consumed."""

    def __init__(self, message: str = "Invalid or expired OAuth state"):
        super().__init__(message=message, provider=None)
        self.code = "OAUTH_STATE_ERROR"


class OAuthExchangeError(OAuthError):
    """Failed to exchange code for token."""

    def __init__(self, message: str, provider: str):
        super().__init__(
            message=f"Token exchange failed: {message}",
            provider=provider,
        )
        self.code = "OAUTH_EXCHANGE_ERROR"


class OAuthRefreshError(OAuthError):
    """Failed to refresh token."""

    def __init__(self, message: str, provider: str):
        super().__init__(
            message=f"Token refresh failed: {message}",
            provider=provider,
        )
        self.code = "OAUTH_REFRESH_ERROR"


class OAuthRevokeError(OAuthError):
    """Failed to revoke token."""

    def __init__(self, message: str, provider: str):
        super().__init__(
            message=f"Token revocation failed: {message}",
            provider=provider,
        )
        self.code = "OAUTH_REVOKE_ERROR"


class OAuthProviderNotFoundError(OAuthError):
    """OAuth provider not supported."""

    def __init__(self, provider: str):
        super().__init__(
            message=f"OAuth provider not found: {provider}",
            provider=provider,
        )
        self.code = "OAUTH_PROVIDER_NOT_FOUND"

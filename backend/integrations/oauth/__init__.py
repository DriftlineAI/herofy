"""
OAuth module for external integrations.
"""

from integrations.oauth.protocol import OAuthProvider, OAuthTokenResponse, OAuthAuthorizationUrl
from integrations.oauth.service import OAuthService
from integrations.oauth.service_dc import OAuthServiceDC
from integrations.oauth.token_manager import TokenManager
from integrations.oauth.state_manager import StateManager
from integrations.oauth.state_manager_dc import StateManagerDC
from integrations.oauth.errors import (
    OAuthError,
    OAuthStateError,
    OAuthExchangeError,
    OAuthRefreshError,
    OAuthRevokeError,
)

__all__ = [
    "OAuthProvider",
    "OAuthTokenResponse",
    "OAuthAuthorizationUrl",
    "OAuthService",
    "OAuthServiceDC",
    "TokenManager",
    "StateManager",
    "StateManagerDC",
    "OAuthError",
    "OAuthStateError",
    "OAuthExchangeError",
    "OAuthRefreshError",
    "OAuthRevokeError",
]

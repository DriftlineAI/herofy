"""
Herofy External Integrations
OAuth flows and API clients for Gmail, Slack, and Notion.
"""

from integrations.oauth.service import OAuthService
from integrations.oauth.token_manager import TokenManager
from integrations.oauth.state_manager import StateManager
from integrations.oauth.errors import (
    OAuthError,
    OAuthStateError,
    OAuthExchangeError,
    OAuthRefreshError,
    OAuthRevokeError,
)


def create_provider_registry(db, config, state_manager):
    """
    Create standard OAuth provider registry.

    Lazy import to avoid circular dependencies.
    """
    from integrations.providers.gmail import GmailOAuthProvider
    from integrations.providers.slack import SlackOAuthProvider
    from integrations.providers.notion import NotionOAuthProvider
    from integrations.providers.notion_mcp import NotionMcpOAuthProvider

    return {
        "gmail": GmailOAuthProvider(db, config, state_manager),
        "slack": SlackOAuthProvider(db, config, state_manager),
        "notion": NotionOAuthProvider(db, config, state_manager),
        "notion_mcp": NotionMcpOAuthProvider(db, config, state_manager),
    }


__all__ = [
    "OAuthService",
    "TokenManager",
    "StateManager",
    "OAuthError",
    "OAuthStateError",
    "OAuthExchangeError",
    "OAuthRefreshError",
    "OAuthRevokeError",
    "create_provider_registry",
]

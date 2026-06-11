"""
Slack OAuth Provider
Implements OAuth 2.0 for Slack API access.
"""

from typing import Any

from integrations.providers.base import BaseOAuthProvider
from integrations.oauth.protocol import OAuthTokenResponse


class SlackOAuthProvider(BaseOAuthProvider):
    """
    Slack OAuth provider.

    Scopes:
    - channels:history: Read public channel messages
    - channels:read: List public channels
    - users:read: Read user profiles
    - users:read.email: Read user email addresses
    - chat:write: Post messages

    Docs: https://api.slack.com/authentication/oauth-v2
    """

    @property
    def provider_name(self) -> str:
        return "slack"

    @property
    def authorization_endpoint(self) -> str:
        return "https://slack.com/oauth/v2/authorize"

    @property
    def token_endpoint(self) -> str:
        return "https://slack.com/api/oauth.v2.access"

    @property
    def revocation_endpoint(self) -> str:
        return "https://slack.com/api/auth.revoke"

    def get_client_credentials(self) -> tuple[str, str]:
        """Get Slack OAuth credentials from config."""
        client_id = self.config.slack_client_id
        client_secret = self.config.slack_client_secret

        if not client_id or not client_secret:
            raise ValueError(
                "Slack OAuth credentials not configured "
                "(slack_client_id/slack_client_secret)"
            )

        return client_id, client_secret

    def get_default_scopes(self) -> list[str]:
        """Default Slack API scopes."""
        return [
            "channels:history",
            "channels:read",
            "users:read",
            "users:read.email",
            "chat:write",
        ]

    def _customize_auth_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Customize for Slack OAuth v2."""
        # Slack uses comma-separated scopes
        if "scope" in params:
            params["scope"] = params["scope"].replace(" ", ",")
        return params

    def _parse_token_response(self, data: dict[str, Any]) -> OAuthTokenResponse:
        """
        Parse Slack's token response format.
        Slack OAuth v2 returns tokens in nested structure.
        """
        # Check for Slack-specific error response
        if not data.get("ok", True):
            error = data.get("error", "unknown_error")
            raise ValueError(f"Slack OAuth error: {error}")

        # Slack OAuth v2 response format
        # Bot token is in access_token, user token in authed_user
        access_token = data.get("access_token")

        # If authed_user exists, prefer user token for user-scoped actions
        if "authed_user" in data:
            user_token = data["authed_user"].get("access_token")
            if user_token:
                access_token = user_token

        return OAuthTokenResponse(
            access_token=access_token,
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
            scope=data.get("scope"),
            token_type="Bearer",
            extra_data={
                "team_id": data.get("team", {}).get("id"),
                "team_name": data.get("team", {}).get("name"),
                "bot_user_id": data.get("bot_user_id"),
                "authed_user_id": data.get("authed_user", {}).get("id"),
            },
        )

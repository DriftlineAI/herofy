"""
OAuth Provider Protocol
Defines interface that all OAuth providers must implement.
"""

from typing import Protocol
from pydantic import BaseModel


class OAuthTokenResponse(BaseModel):
    """Standard token response across all providers."""

    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None  # seconds
    scope: str | None = None
    token_type: str = "Bearer"
    # Provider-specific metadata
    extra_data: dict | None = None


class OAuthAuthorizationUrl(BaseModel):
    """Authorization URL with state."""

    url: str
    state: str


class OAuthProvider(Protocol):
    """
    Protocol that all OAuth providers must implement.
    Ensures consistent interface across Gmail, Slack, Notion, etc.
    """

    @property
    def provider_name(self) -> str:
        """Provider name (gmail, slack, notion, hubspot)."""
        ...

    async def get_authorization_url(
        self,
        workspace_id: str,
        user_id: str,
        redirect_uri: str,
        scopes: list[str] | None = None,
    ) -> OAuthAuthorizationUrl:
        """
        Generate OAuth authorization URL.

        Args:
            workspace_id: Workspace connecting the integration
            user_id: Firebase user UID
            redirect_uri: Callback URL
            scopes: Optional scope override (uses defaults if None)

        Returns:
            Authorization URL with state parameter
        """
        ...

    async def exchange_code(
        self,
        code: str,
        state: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> OAuthTokenResponse:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from callback
            state: State parameter (for validation)
            redirect_uri: Must match the one used in authorization
            code_verifier: PKCE verifier (PKCE providers only; others ignore it)

        Returns:
            Access token, refresh token, and metadata

        Raises:
            OAuthStateError: If state is invalid or expired
            OAuthExchangeError: If token exchange fails
        """
        ...

    async def refresh_access_token(
        self,
        refresh_token: str,
    ) -> OAuthTokenResponse:
        """
        Refresh an expired access token.

        Args:
            refresh_token: Valid refresh token

        Returns:
            New access token (and possibly new refresh token)

        Raises:
            OAuthRefreshError: If refresh fails
        """
        ...

    async def revoke_token(
        self,
        token: str,
    ) -> None:
        """
        Revoke an access token with the provider.

        Args:
            token: Access or refresh token to revoke
        """
        ...

    def get_default_scopes(self) -> list[str]:
        """Get default OAuth scopes for this provider."""
        ...

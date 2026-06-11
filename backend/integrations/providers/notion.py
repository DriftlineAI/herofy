"""
Notion OAuth Provider
Implements OAuth 2.0 for Notion API access.
"""

import base64
from typing import Any

import httpx

from integrations.providers.base import BaseOAuthProvider
from integrations.oauth.protocol import OAuthTokenResponse
from integrations.oauth.errors import OAuthExchangeError, OAuthRefreshError
from core.logging import get_logger

logger = get_logger("NotionOAuthProvider")


class NotionOAuthProvider(BaseOAuthProvider):
    """
    Notion OAuth provider.

    Notion OAuth uses a different token exchange format:
    - Basic auth with client_id:client_secret
    - JSON body instead of form data
    - No refresh tokens (tokens are long-lived)

    Docs: https://developers.notion.com/docs/authorization
    """

    @property
    def provider_name(self) -> str:
        return "notion"

    @property
    def authorization_endpoint(self) -> str:
        return "https://api.notion.com/v1/oauth/authorize"

    @property
    def token_endpoint(self) -> str:
        return "https://api.notion.com/v1/oauth/token"

    @property
    def revocation_endpoint(self) -> str | None:
        # Notion doesn't have a revocation endpoint
        return None

    def get_client_credentials(self) -> tuple[str, str]:
        """Get Notion OAuth credentials from config."""
        client_id = self.config.notion_client_id
        client_secret = self.config.notion_client_secret

        if not client_id or not client_secret:
            raise ValueError(
                "Notion OAuth credentials not configured "
                "(notion_client_id/notion_client_secret)"
            )

        return client_id, client_secret

    def get_default_scopes(self) -> list[str]:
        """Notion doesn't use scopes - access is granted per-database."""
        return []

    def _customize_auth_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Notion uses 'owner' parameter instead of 'scope'."""
        # Remove scope parameter (not used by Notion)
        params.pop("scope", None)

        # Notion requires owner=user for user grants
        params["owner"] = "user"

        return params

    async def exchange_code(
        self,
        code: str,
        state: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> OAuthTokenResponse:
        """
        Exchange authorization code for access token.

        Notion uses Basic auth and JSON body for token exchange.
        `code_verifier` is the PKCE verifier; standard Notion OAuth doesn't use PKCE,
        so it's accepted for interface compatibility and ignored.
        """
        client_id, client_secret = self.get_client_credentials()

        # Notion requires Basic auth
        auth_string = f"{client_id}:{client_secret}"
        auth_header = base64.b64encode(auth_string.encode()).decode()

        headers = {
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }

        body = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }

        try:
            response = await self.http_client.post(
                self.token_endpoint,
                headers=headers,
                json=body,
            )
            response.raise_for_status()
            token_data = response.json()

            logger.info(
                "token_exchange_success",
                provider=self.provider_name,
            )

            return self._parse_token_response(token_data)

        except httpx.HTTPStatusError as e:
            error_body = e.response.text
            logger.error(
                "token_exchange_failed",
                provider=self.provider_name,
                status=e.response.status_code,
                error=error_body,
            )
            raise OAuthExchangeError(
                f"HTTP {e.response.status_code}: {error_body}",
                provider=self.provider_name,
            )
        except Exception as e:
            logger.error(
                "token_exchange_error",
                provider=self.provider_name,
                error=str(e),
            )
            raise OAuthExchangeError(str(e), provider=self.provider_name)

    async def refresh_access_token(
        self,
        refresh_token: str,
    ) -> OAuthTokenResponse:
        """
        Notion doesn't support token refresh.
        Tokens are long-lived and user must re-authorize when expired.
        """
        raise OAuthRefreshError(
            "Notion does not support token refresh - user must re-authorize",
            provider=self.provider_name,
        )

    def _parse_token_response(self, data: dict[str, Any]) -> OAuthTokenResponse:
        """Parse Notion's token response format."""
        return OAuthTokenResponse(
            access_token=data["access_token"],
            refresh_token=None,  # Notion doesn't provide refresh tokens
            expires_in=None,  # Notion tokens are long-lived
            scope=None,
            token_type=data.get("token_type", "Bearer"),
            extra_data={
                "workspace_id": data.get("workspace_id"),
                "workspace_name": data.get("workspace_name"),
                "workspace_icon": data.get("workspace_icon"),
                "bot_id": data.get("bot_id"),
                "owner": data.get("owner"),
                "duplicated_template_id": data.get("duplicated_template_id"),
            },
        )

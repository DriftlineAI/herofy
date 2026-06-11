"""
Base OAuth Provider
Shared logic for all OAuth providers.
"""

from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlencode

import httpx

from db.client import DatabaseClient
from config import Settings
from core.logging import get_logger
from core.types import IntegrationType
from integrations.oauth.protocol import OAuthAuthorizationUrl, OAuthTokenResponse
from integrations.oauth.state_manager import StateManager
from integrations.oauth.errors import OAuthExchangeError, OAuthRefreshError, OAuthRevokeError

logger = get_logger("BaseOAuthProvider")


class BaseOAuthProvider(ABC):
    """
    Base class for OAuth providers.
    Implements common OAuth 2.0 flow logic.
    """

    def __init__(
        self,
        db: DatabaseClient,
        config: Settings,
        state_manager: StateManager,
    ):
        """
        Initialize provider.

        Args:
            db: Database client
            config: Application settings
            state_manager: OAuth state manager
        """
        self.db = db
        self.config = config
        self.state_manager = state_manager
        self._http_client: httpx.AsyncClient | None = None

    @property
    def http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier (gmail, slack, notion, etc.)."""
        pass

    @property
    @abstractmethod
    def authorization_endpoint(self) -> str:
        """OAuth authorization URL."""
        pass

    @property
    @abstractmethod
    def token_endpoint(self) -> str:
        """OAuth token exchange URL."""
        pass

    @property
    def revocation_endpoint(self) -> str | None:
        """OAuth token revocation URL (optional, override in subclass)."""
        return None

    @abstractmethod
    def get_client_credentials(self) -> tuple[str, str]:
        """
        Get client ID and secret from config.

        Returns:
            (client_id, client_secret)
        """
        pass

    @abstractmethod
    def get_default_scopes(self) -> list[str]:
        """Get default OAuth scopes for this provider."""
        pass

    def _get_integration_type(self) -> IntegrationType:
        """Get IntegrationType enum for this provider."""
        return IntegrationType(self.provider_name)

    async def get_authorization_url(
        self,
        workspace_id: str,
        user_id: str,
        redirect_uri: str,
        scopes: list[str] | None = None,
    ) -> OAuthAuthorizationUrl:
        """
        Generate OAuth authorization URL.

        Implements OAuth 2.0 Authorization Code Flow.
        """
        # Create state for CSRF protection
        state = await self.state_manager.create_state(
            workspace_id=workspace_id,
            user_id=user_id,
            integration_type=self._get_integration_type(),
            redirect_uri=redirect_uri,
        )

        client_id, _ = self.get_client_credentials()
        scopes = scopes or self.get_default_scopes()

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
        }

        # Only add scope if provider uses scopes
        if scopes:
            params["scope"] = " ".join(scopes)

        # Allow subclasses to modify params
        params = self._customize_auth_params(params)

        url = f"{self.authorization_endpoint}?{urlencode(params)}"

        logger.info(
            "authorization_url_generated",
            provider=self.provider_name,
            workspace_id=workspace_id,
            scopes=scopes,
        )

        return OAuthAuthorizationUrl(url=url, state=state)

    def _customize_auth_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Hook for providers to customize authorization parameters.
        Override in subclass if needed.
        """
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

        Implements OAuth 2.0 token exchange.

        Note: State validation should be done by OAuthService before calling this.
        `code_verifier` is the PKCE verifier (used by providers that require PKCE, e.g.
        notion_mcp); standard providers ignore it.
        """
        client_id, client_secret = self.get_client_credentials()

        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        # Allow subclasses to customize token request
        data = self._customize_token_request(data)

        try:
            response = await self.http_client.post(
                self.token_endpoint,
                data=data,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            token_data = response.json()

            logger.info(
                "token_exchange_success",
                provider=self.provider_name,
            )

            return self._parse_token_response(token_data)

        except httpx.HTTPStatusError as e:
            # Truncate error body to avoid logging tokens
            error_body = e.response.text[:200] if e.response.text else "No response body"
            logger.error(
                "token_exchange_failed",
                provider=self.provider_name,
                status=e.response.status_code,
                error=error_body,
            )
            raise OAuthExchangeError(
                f"HTTP {e.response.status_code}",
                provider=self.provider_name,
            )
        except Exception as e:
            logger.error(
                "token_exchange_error",
                provider=self.provider_name,
                error=str(e),
            )
            raise OAuthExchangeError(str(e), provider=self.provider_name)

    def _customize_token_request(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Hook for providers to customize token request.
        Override in subclass if needed.
        """
        return data

    async def refresh_access_token(
        self,
        refresh_token: str,
    ) -> OAuthTokenResponse:
        """Refresh an expired access token."""
        client_id, client_secret = self.get_client_credentials()

        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        try:
            response = await self.http_client.post(
                self.token_endpoint,
                data=data,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            token_data = response.json()

            logger.info(
                "token_refresh_success",
                provider=self.provider_name,
            )

            return self._parse_token_response(token_data)

        except httpx.HTTPStatusError as e:
            # Truncate error body to avoid logging tokens
            error_body = e.response.text[:200] if e.response.text else "No response body"
            logger.error(
                "token_refresh_failed",
                provider=self.provider_name,
                status=e.response.status_code,
                error=error_body,
            )
            raise OAuthRefreshError(
                f"HTTP {e.response.status_code}",
                provider=self.provider_name,
            )
        except Exception as e:
            logger.error(
                "token_refresh_error",
                provider=self.provider_name,
                error=str(e),
            )
            raise OAuthRefreshError(str(e), provider=self.provider_name)

    async def revoke_token(self, token: str) -> None:
        """Revoke an access token."""
        if not self.revocation_endpoint:
            logger.info(
                "revocation_not_supported",
                provider=self.provider_name,
            )
            return

        try:
            client_id, client_secret = self.get_client_credentials()

            data = {
                "token": token,
                "client_id": client_id,
                "client_secret": client_secret,
            }

            response = await self.http_client.post(
                self.revocation_endpoint,
                data=data,
            )
            response.raise_for_status()

            logger.info("token_revoked", provider=self.provider_name)

        except Exception as e:
            logger.error(
                "token_revocation_error",
                provider=self.provider_name,
                error=str(e),
            )
            raise OAuthRevokeError(str(e), provider=self.provider_name)

    def _parse_token_response(self, data: dict[str, Any]) -> OAuthTokenResponse:
        """
        Parse token response from provider.
        Override in subclass if provider uses non-standard format.
        """
        return OAuthTokenResponse(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
            scope=data.get("scope"),
            token_type=data.get("token_type", "Bearer"),
            extra_data=None,
        )

    async def cleanup(self) -> None:
        """Cleanup resources (close HTTP client)."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

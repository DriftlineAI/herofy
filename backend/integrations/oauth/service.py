"""
OAuth Service
Orchestrates OAuth flows across providers.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from db.client import DatabaseClient
from config import Settings
from core.logging import get_logger
from core.types import IntegrationType, IntegrationStatus
from integrations.oauth.protocol import OAuthProvider, OAuthAuthorizationUrl, OAuthTokenResponse
from integrations.oauth.token_manager import TokenManager
from integrations.oauth.state_manager import StateManager
from integrations.oauth.errors import OAuthError, OAuthProviderNotFoundError

logger = get_logger("OAuthService")


class OAuthService:
    """
    High-level OAuth service.

    Coordinates:
    - Provider-specific OAuth handlers
    - Token encryption/decryption
    - State management
    - Database persistence
    """

    def __init__(
        self,
        db: DatabaseClient,
        config: Settings,
        token_manager: TokenManager,
        state_manager: StateManager,
        providers: dict[str, OAuthProvider],
    ):
        """
        Initialize OAuthService.

        Args:
            db: Database client
            config: Application settings
            token_manager: Token encryption manager
            state_manager: OAuth state manager
            providers: Dictionary of provider_name -> OAuthProvider
        """
        self.db = db
        self.config = config
        self.token_manager = token_manager
        self.state_manager = state_manager
        self.providers = providers

    def get_provider(self, integration_type: IntegrationType | str) -> OAuthProvider:
        """
        Get OAuth provider by integration type.

        Args:
            integration_type: Integration type enum or string

        Returns:
            OAuth provider instance

        Raises:
            OAuthProviderNotFoundError: If provider not found
        """
        if isinstance(integration_type, IntegrationType):
            provider_name = integration_type.value
        else:
            provider_name = integration_type

        provider = self.providers.get(provider_name)
        if not provider:
            raise OAuthProviderNotFoundError(provider_name)

        return provider

    async def start_oauth_flow(
        self,
        workspace_id: str | UUID,
        user_id: str,
        integration_type: IntegrationType | str,
        redirect_uri: str,
        scopes: list[str] | None = None,
    ) -> OAuthAuthorizationUrl:
        """
        Start OAuth authorization flow.

        Args:
            workspace_id: Workspace ID
            user_id: Firebase user UID
            integration_type: Type of integration
            redirect_uri: Callback URL
            scopes: Optional custom scopes

        Returns:
            Authorization URL to redirect user to
        """
        provider = self.get_provider(integration_type)

        auth_url = await provider.get_authorization_url(
            workspace_id=str(workspace_id),
            user_id=user_id,
            redirect_uri=redirect_uri,
            scopes=scopes,
        )

        logger.info(
            "oauth_flow_started",
            workspace_id=str(workspace_id),
            integration_type=str(integration_type),
            provider=provider.provider_name,
        )

        return auth_url

    async def complete_oauth_flow(
        self,
        code: str,
        state: str,
        redirect_uri: str,
    ) -> dict[str, Any]:
        """
        Complete OAuth flow after callback.

        Args:
            code: Authorization code from provider
            state: State parameter (for validation)
            redirect_uri: Callback URI (must match)

        Returns:
            Dict with workspace_id, user_id, integration_type, success status

        Raises:
            OAuthError: If flow fails
        """
        # Validate and consume state
        state_record = await self.state_manager.consume_state(state)

        workspace_id = state_record["workspace_id"]
        user_id = state_record["user_id"]
        integration_type = state_record["integration_type"]

        provider = self.get_provider(integration_type)

        try:
            # Exchange code for tokens (pass the PKCE verifier stored with the state, if any —
            # providers that don't use PKCE ignore it).
            token_response = await provider.exchange_code(
                code=code,
                state=state,
                redirect_uri=redirect_uri,
                code_verifier=state_record.get("code_verifier"),
            )

            # Encrypt tokens
            encrypted_access_token = self.token_manager.encrypt(token_response.access_token)
            encrypted_refresh_token = (
                self.token_manager.encrypt(token_response.refresh_token)
                if token_response.refresh_token
                else None
            )

            # Calculate expiry
            token_expires_at = None
            if token_response.expires_in:
                token_expires_at = datetime.now(timezone.utc) + timedelta(
                    seconds=token_response.expires_in
                )

            # Build config from extra data
            config = {}
            if token_response.scope:
                config["scope"] = token_response.scope
            if token_response.extra_data:
                config.update(token_response.extra_data)

            # Store in database
            await self._store_integration(
                workspace_id=workspace_id,
                integration_type=integration_type,
                access_token=encrypted_access_token,
                refresh_token=encrypted_refresh_token,
                token_expires_at=token_expires_at,
                config=config,
                connected_by_user_id=user_id,
            )

            logger.info(
                "oauth_flow_completed",
                workspace_id=workspace_id,
                integration_type=integration_type,
                provider=provider.provider_name,
            )

            return {
                "workspace_id": workspace_id,
                "user_id": user_id,
                "integration_type": integration_type,
                "success": True,
            }

        except Exception as e:
            logger.error(
                "oauth_flow_failed",
                workspace_id=workspace_id,
                integration_type=integration_type,
                error=str(e),
            )
            raise

    async def refresh_token(
        self,
        workspace_id: str | UUID,
        integration_type: IntegrationType | str,
    ) -> str:
        """
        Refresh an expired access token.

        Args:
            workspace_id: Workspace ID
            integration_type: Integration type

        Returns:
            New decrypted access token

        Raises:
            OAuthError: If refresh fails
        """
        provider = self.get_provider(integration_type)

        # Get current integration
        integration = await self._get_integration(workspace_id, integration_type)

        if not integration or not integration.get("refresh_token"):
            raise OAuthError(
                f"No refresh token available for {integration_type}",
                provider=str(integration_type),
            )

        # Decrypt refresh token
        refresh_token = self.token_manager.decrypt(integration["refresh_token"])

        # Refresh with provider
        token_response = await provider.refresh_access_token(refresh_token)

        # Encrypt new tokens
        encrypted_access_token = self.token_manager.encrypt(token_response.access_token)
        encrypted_refresh_token = (
            self.token_manager.encrypt(token_response.refresh_token)
            if token_response.refresh_token
            else integration["refresh_token"]  # Keep old refresh token if not returned
        )

        # Calculate expiry
        token_expires_at = None
        if token_response.expires_in:
            token_expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=token_response.expires_in
            )

        # Update database
        type_str = (
            integration_type.value
            if isinstance(integration_type, IntegrationType)
            else integration_type
        )

        await self.db.execute(
            """
            UPDATE workspace_integrations
            SET access_token = $1,
                refresh_token = $2,
                token_expires_at = $3,
                updated_at = $4,
                last_error = NULL,
                error_count = 0
            WHERE workspace_id = $5 AND integration_type = $6
            """,
            [
                encrypted_access_token,
                encrypted_refresh_token,
                token_expires_at,
                datetime.now(timezone.utc),
                str(workspace_id),
                type_str,
            ],
        )

        logger.info(
            "token_refreshed",
            workspace_id=str(workspace_id),
            integration_type=type_str,
        )

        return token_response.access_token

    async def revoke_integration(
        self,
        workspace_id: str | UUID,
        integration_type: IntegrationType | str,
    ) -> None:
        """
        Revoke OAuth integration.

        Args:
            workspace_id: Workspace ID
            integration_type: Integration type
        """
        provider = self.get_provider(integration_type)
        integration = await self._get_integration(workspace_id, integration_type)

        if integration and integration.get("access_token"):
            try:
                # Decrypt and revoke with provider
                access_token = self.token_manager.decrypt(integration["access_token"])
                await provider.revoke_token(access_token)
            except Exception as e:
                logger.warning(
                    "provider_revocation_failed",
                    integration_type=str(integration_type),
                    error=str(e),
                )

        # Mark as revoked in database
        type_str = (
            integration_type.value
            if isinstance(integration_type, IntegrationType)
            else integration_type
        )

        await self.db.execute(
            """
            UPDATE workspace_integrations
            SET status = $1,
                access_token = NULL,
                refresh_token = NULL,
                updated_at = $2
            WHERE workspace_id = $3 AND integration_type = $4
            """,
            [
                IntegrationStatus.REVOKED.value,
                datetime.now(timezone.utc),
                str(workspace_id),
                type_str,
            ],
        )

        logger.info(
            "integration_revoked",
            workspace_id=str(workspace_id),
            integration_type=type_str,
        )

    async def get_decrypted_token(
        self,
        workspace_id: str | UUID,
        integration_type: IntegrationType | str,
    ) -> str:
        """
        Get decrypted access token for an integration.

        Does NOT automatically refresh - use IntegrationService.get_valid_token() for that.

        Args:
            workspace_id: Workspace ID
            integration_type: Integration type

        Returns:
            Decrypted access token

        Raises:
            OAuthError: If no integration or token found
        """
        integration = await self._get_integration(workspace_id, integration_type)

        if not integration or not integration.get("access_token"):
            raise OAuthError(
                f"No access token found for {integration_type}",
                provider=str(integration_type),
            )

        return self.token_manager.decrypt(integration["access_token"])

    async def _store_integration(
        self,
        workspace_id: str,
        integration_type: str,
        access_token: str,
        refresh_token: str | None,
        token_expires_at: datetime | None,
        config: dict[str, Any],
        connected_by_user_id: str,
    ) -> None:
        """Store or update integration in database."""
        import json

        await self.db.execute(
            """
            INSERT INTO workspace_integrations (
                workspace_id, integration_type, access_token, refresh_token,
                token_expires_at, config, status, connected_by_user_id,
                created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $9)
            ON CONFLICT (workspace_id, integration_type)
            DO UPDATE SET
                access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                token_expires_at = EXCLUDED.token_expires_at,
                config = EXCLUDED.config,
                status = EXCLUDED.status,
                connected_by_user_id = EXCLUDED.connected_by_user_id,
                updated_at = EXCLUDED.updated_at,
                last_error = NULL,
                error_count = 0
            """,
            [
                workspace_id,
                integration_type,
                access_token,
                refresh_token,
                token_expires_at,
                json.dumps(config),
                IntegrationStatus.ACTIVE.value,
                connected_by_user_id,
                datetime.now(timezone.utc),
            ],
        )

    async def _get_integration(
        self,
        workspace_id: str | UUID,
        integration_type: IntegrationType | str,
    ) -> dict[str, Any] | None:
        """Get integration from database."""
        if isinstance(integration_type, IntegrationType):
            integration_type = integration_type.value

        return await self.db.query_one(
            """
            SELECT * FROM workspace_integrations
            WHERE workspace_id = $1 AND integration_type = $2
            """,
            [str(workspace_id), integration_type],
        )

    async def list_integrations(
        self,
        workspace_id: str | UUID,
    ) -> list[dict[str, Any]]:
        """
        List all integrations for a workspace.

        Args:
            workspace_id: Workspace ID

        Returns:
            List of integration records (without decrypted tokens)
        """
        integrations = await self.db.query(
            """
            SELECT
                workspace_id, integration_type, status,
                token_expires_at, config, last_sync_at,
                last_error, error_count, connected_by_user_id,
                created_at, updated_at
            FROM workspace_integrations
            WHERE workspace_id = $1
            ORDER BY integration_type
            """,
            [str(workspace_id)],
        )

        return integrations

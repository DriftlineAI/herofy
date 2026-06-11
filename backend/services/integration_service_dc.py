"""
Integration Service (DataConnect Version)
Business logic for workspace integrations using Firebase Data Connect

This is the DataConnect-based version of IntegrationService.
It uses GraphQL operations instead of raw SQL queries.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING

from db.dataconnect_client import DataConnectClient
from core.logging import get_logger
from core.types import IntegrationType, IntegrationStatus
from core.errors import IntegrationNotConfiguredError, IntegrationTokenExpiredError

if TYPE_CHECKING:
    from integrations.oauth.token_manager import TokenManager
    from integrations.oauth.service import OAuthService

logger = get_logger("IntegrationServiceDC")


class IntegrationServiceDC:
    """
    Service for managing workspace integrations using DataConnect.

    This is a drop-in replacement for IntegrationService that uses
    Firebase Data Connect GraphQL API instead of direct PostgreSQL.
    """

    def __init__(
        self,
        dc: DataConnectClient,
        workspace_id: str,
        token_manager: "TokenManager | None" = None,
        oauth_service: "OAuthService | None" = None,
    ):
        """
        Initialize IntegrationServiceDC.

        Args:
            dc: DataConnect client
            workspace_id: Workspace ID
            token_manager: Optional TokenManager for encryption (lazy-loaded if not provided)
            oauth_service: Optional OAuthService for token refresh (lazy-loaded if not provided)
        """
        self.dc = dc
        self.workspace_id = workspace_id
        self._token_manager = token_manager
        self._oauth_service = oauth_service

    @property
    def token_manager(self) -> "TokenManager":
        """Get token manager (lazy-loaded)."""
        if self._token_manager is None:
            from integrations.oauth.token_manager import TokenManager
            self._token_manager = TokenManager()
        return self._token_manager

    async def get_integration(
        self,
        integration_type: IntegrationType | str,
    ) -> dict[str, Any] | None:
        """
        Get an integration configuration for the workspace.

        Args:
            integration_type: Type of integration

        Returns:
            Integration record or None if not configured
        """
        if isinstance(integration_type, IntegrationType):
            integration_type = integration_type.value

        result = await self.dc.execute_query(
            "GetWorkspaceIntegration",
            {
                "workspaceId": self.workspace_id,
                "integrationType": integration_type,
            },
        )

        integrations = result.get("workspaceIntegrations", [])
        if not integrations:
            return None

        # Convert GraphQL response to match legacy format
        integration = integrations[0]
        return self._to_legacy_format(integration)

    def _to_legacy_format(self, integration: dict[str, Any]) -> dict[str, Any]:
        """Convert GraphQL response format to legacy SQL format."""
        import json

        # Parse config from JSON string if needed
        config = integration.get("config")
        if config and isinstance(config, str):
            try:
                config = json.loads(config)
            except json.JSONDecodeError:
                config = {}

        return {
            "workspace_id": self.workspace_id,
            "integration_type": integration.get("integrationType"),
            "access_token": integration.get("accessToken"),
            "refresh_token": integration.get("refreshToken"),
            "token_expires_at": integration.get("tokenExpiresAt"),
            "status": integration.get("status"),
            "config": config,
            "last_sync_at": integration.get("lastSyncAt"),
            "last_error": integration.get("lastError"),
            "error_count": integration.get("errorCount"),
            "created_at": integration.get("createdAt"),
            "updated_at": integration.get("updatedAt"),
            "connected_by_user_id": (integration.get("connectedByUser") or {}).get("id"),
        }

    async def get_active_integration(
        self,
        integration_type: IntegrationType | str,
    ) -> dict[str, Any]:
        """
        Get an active integration, raising error if not configured.

        Args:
            integration_type: Type of integration

        Returns:
            Active integration record

        Raises:
            IntegrationNotConfiguredError: If integration not set up
        """
        if isinstance(integration_type, IntegrationType):
            type_str = integration_type.value
        else:
            type_str = integration_type

        integration = await self.get_integration(type_str)

        if not integration:
            raise IntegrationNotConfiguredError(self.workspace_id, type_str)

        if integration["status"] != IntegrationStatus.ACTIVE.value:
            raise IntegrationNotConfiguredError(self.workspace_id, type_str)

        return integration

    async def create_integration(
        self,
        integration_type: IntegrationType | str,
        access_token: str,
        refresh_token: str | None = None,
        token_expires_at: datetime | None = None,
        config: dict[str, Any] | None = None,
        connected_by_user_id: str | None = None,
        encrypt_tokens: bool = True,
    ) -> dict[str, Any]:
        """
        Create or update an integration for the workspace.

        Args:
            integration_type: Type of integration
            access_token: OAuth access token
            refresh_token: OAuth refresh token (if available)
            token_expires_at: When the token expires
            config: Integration-specific configuration
            connected_by_user_id: User who connected the integration
            encrypt_tokens: Whether to encrypt tokens (default True)

        Returns:
            Created/updated integration record
        """
        if isinstance(integration_type, IntegrationType):
            integration_type = integration_type.value

        # Encrypt tokens if encryption is enabled
        if encrypt_tokens:
            encrypted_access_token = self.token_manager.encrypt(access_token)
            encrypted_refresh_token = (
                self.token_manager.encrypt(refresh_token) if refresh_token else None
            )
        else:
            encrypted_access_token = access_token
            encrypted_refresh_token = refresh_token

        # Serialize config to JSON string
        import json
        config_str = json.dumps(config or {})

        # Convert datetime to ISO string
        token_expires_str = None
        if token_expires_at:
            token_expires_str = token_expires_at.isoformat()

        result = await self.dc.execute_mutation(
            "UpsertWorkspaceIntegration",
            {
                "workspaceId": self.workspace_id,
                "integrationType": integration_type,
                "accessToken": encrypted_access_token,
                "refreshToken": encrypted_refresh_token,
                "tokenExpiresAt": token_expires_str,
                "config": config_str,
                "status": IntegrationStatus.ACTIVE.value,
            },
        )

        logger.info(
            "integration_created",
            integration_type=integration_type,
            workspace_id=self.workspace_id,
        )

        # Return the integration data
        return await self.get_integration(integration_type) or {}

    async def update_config(
        self,
        integration_type: IntegrationType | str,
        config: dict[str, Any],
        merge: bool = True,
    ) -> dict[str, Any]:
        """
        Update integration configuration.

        Args:
            integration_type: Type of integration
            config: New configuration values
            merge: If True, merge with existing config. If False, replace.

        Returns:
            Updated integration record
        """
        integration = await self.get_active_integration(integration_type)

        if merge:
            import json
            existing_config = {}
            if integration.get("config"):
                existing_config = json.loads(integration["config"]) if isinstance(integration["config"], str) else integration["config"]
            new_config = {**existing_config, **config}
        else:
            new_config = config

        import json
        if isinstance(integration_type, IntegrationType):
            integration_type = integration_type.value

        await self.dc.execute_mutation(
            "UpsertWorkspaceIntegration",
            {
                "workspaceId": self.workspace_id,
                "integrationType": integration_type,
                "config": json.dumps(new_config),
                "status": integration["status"],
            },
        )

        return await self.get_integration(integration_type) or {}

    async def get_valid_token(
        self,
        integration_type: IntegrationType | str,
    ) -> str:
        """
        Get a valid access token, refreshing if needed.

        Args:
            integration_type: Type of integration

        Returns:
            Valid (decrypted) access token

        Raises:
            IntegrationTokenExpiredError: If token is expired and can't be refreshed
        """
        if isinstance(integration_type, IntegrationType):
            type_str = integration_type.value
        else:
            type_str = integration_type

        integration = await self.get_active_integration(type_str)

        # Check if token is expired
        expires_at = integration.get("token_expires_at")
        if expires_at:
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))

            # Add buffer to avoid edge cases
            if expires_at < datetime.now(timezone.utc) + timedelta(minutes=5):
                # Try to refresh
                if integration.get("refresh_token"):
                    try:
                        return await self._refresh_token(integration, type_str)
                    except Exception as e:
                        logger.error(
                            "token_refresh_failed",
                            integration_type=type_str,
                            error=str(e),
                        )
                        raise IntegrationTokenExpiredError(
                            self.workspace_id, type_str
                        )
                else:
                    raise IntegrationTokenExpiredError(self.workspace_id, type_str)

        # Decrypt and return token
        encrypted_token = integration["access_token"]
        return self.token_manager.decrypt(encrypted_token)

    async def _refresh_token(
        self,
        integration: dict[str, Any],
        integration_type: str,
    ) -> str:
        """
        Refresh an OAuth token.

        Uses OAuthService if available, otherwise raises error.

        Args:
            integration: Integration record with refresh_token
            integration_type: Type of integration

        Returns:
            New (decrypted) access token
        """
        if self._oauth_service is None:
            # Try to create OAuthService dynamically
            try:
                from integrations.oauth.service import OAuthService
                from integrations.oauth.state_manager import StateManager
                from integrations import create_provider_registry
                from config import settings
                # StateManager requires asyncpg DatabaseClient for raw SQL queries
                # During migration, both asyncpg and DataConnect are initialized
                from db.client import get_db_client

                db = get_db_client()
                state_manager = StateManager(db)
                providers = create_provider_registry(db, settings, state_manager)
                self._oauth_service = OAuthService(
                    db, settings, self.token_manager, state_manager, providers
                )
            except Exception as e:
                logger.error("oauth_service_init_failed", error=str(e))
                raise IntegrationTokenExpiredError(self.workspace_id, integration_type)

        # Use OAuthService to refresh
        return await self._oauth_service.refresh_token(
            workspace_id=self.workspace_id,
            integration_type=integration_type,
        )

    async def record_sync(self, integration_type: IntegrationType | str) -> None:
        """
        Record a successful sync for an integration.

        Args:
            integration_type: Type of integration
        """
        if isinstance(integration_type, IntegrationType):
            integration_type = integration_type.value

        await self.dc.execute_mutation(
            "RecordIntegrationSync",
            {
                "workspaceId": self.workspace_id,
                "integrationType": integration_type,
            },
        )

    async def record_error(
        self,
        integration_type: IntegrationType | str,
        error: str,
    ) -> None:
        """
        Record an error for an integration.

        Args:
            integration_type: Type of integration
            error: Error message
        """
        integration = await self.get_integration(integration_type)
        if integration:
            error_count = integration.get("error_count", 0) + 1
            status = integration["status"]

            # Mark as error after 3 consecutive failures
            if error_count >= 3:
                status = IntegrationStatus.ERROR.value
                logger.warning(
                    "integration_marked_error",
                    integration_type=integration_type if isinstance(integration_type, str) else integration_type.value,
                    error_count=error_count,
                )

            if isinstance(integration_type, IntegrationType):
                integration_type = integration_type.value

            await self.dc.execute_mutation(
                "UpdateIntegrationStatus",
                {
                    "workspaceId": self.workspace_id,
                    "integrationType": integration_type,
                    "status": status,
                    "lastError": error,
                    "errorCount": error_count,
                },
            )

    async def revoke_integration(
        self,
        integration_type: IntegrationType | str,
    ) -> dict[str, Any] | None:
        """
        Revoke an integration.

        Args:
            integration_type: Type of integration

        Returns:
            Updated integration record
        """
        integration = await self.get_integration(integration_type)
        if not integration:
            return None

        if isinstance(integration_type, IntegrationType):
            integration_type = integration_type.value

        await self.dc.execute_mutation(
            "RevokeIntegration",
            {
                "workspaceId": self.workspace_id,
                "integrationType": integration_type,
            },
        )

        return await self.get_integration(integration_type)

    async def list_integrations(self) -> list[dict[str, Any]]:
        """
        List all integrations for the workspace.

        Returns:
            List of integration records
        """
        result = await self.dc.execute_query(
            "GetWorkspaceIntegrations",
            {"workspaceId": self.workspace_id},
        )

        integrations = result.get("workspaceIntegrations", [])
        return [self._to_legacy_format(i) for i in integrations]

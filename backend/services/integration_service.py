"""
Integration Service
Business logic for workspace integrations (OAuth tokens, configs)
"""

from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING

from db.client import DatabaseClient
from core.logging import get_logger
from core.types import IntegrationType, IntegrationStatus
from core.errors import IntegrationNotConfiguredError, IntegrationTokenExpiredError

if TYPE_CHECKING:
    from integrations.oauth.token_manager import TokenManager
    from integrations.oauth.service import OAuthService

logger = get_logger("IntegrationService")


class IntegrationService:
    """Service for managing workspace integrations."""

    def __init__(
        self,
        db: DatabaseClient,
        workspace_id: str,
        token_manager: "TokenManager | None" = None,
        oauth_service: "OAuthService | None" = None,
    ):
        """
        Initialize IntegrationService.

        Args:
            db: Database client
            workspace_id: Workspace ID
            token_manager: Optional TokenManager for encryption (lazy-loaded if not provided)
            oauth_service: Optional OAuthService for token refresh (lazy-loaded if not provided)
        """
        self.db = db
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

        return await self.db.query_one(
            """
            SELECT * FROM workspace_integrations
            WHERE workspace_id = $1 AND integration_type = $2
            """,
            [self.workspace_id, integration_type],
        )

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

        existing = await self.get_integration(integration_type)

        # Encrypt tokens if encryption is enabled
        if encrypt_tokens:
            encrypted_access_token = self.token_manager.encrypt(access_token)
            encrypted_refresh_token = (
                self.token_manager.encrypt(refresh_token) if refresh_token else None
            )
        else:
            encrypted_access_token = access_token
            encrypted_refresh_token = refresh_token

        data = {
            "workspace_id": self.workspace_id,
            "integration_type": integration_type,
            "access_token": encrypted_access_token,
            "refresh_token": encrypted_refresh_token,
            "token_expires_at": token_expires_at,
            "config": config or {},
            "status": IntegrationStatus.ACTIVE.value,
            "connected_by_user_id": connected_by_user_id,
            "last_error": None,
            "error_count": 0,
        }

        if existing:
            integration = await self.db.update(
                "workspace_integrations",
                existing["id"],
                data,
            )
            logger.info(
                "integration_updated",
                integration_type=integration_type,
                workspace_id=self.workspace_id,
            )
        else:
            integration = await self.db.insert("workspace_integrations", data)
            logger.info(
                "integration_created",
                integration_type=integration_type,
                workspace_id=self.workspace_id,
            )

        return integration

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
            new_config = {**integration.get("config", {}), **config}
        else:
            new_config = config

        return await self.db.update(
            "workspace_integrations",
            integration["id"],
            {"config": new_config},
        )

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

                state_manager = StateManager(self.db)
                providers = create_provider_registry(self.db, settings, state_manager)
                self._oauth_service = OAuthService(
                    self.db, settings, self.token_manager, state_manager, providers
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
        integration = await self.get_integration(integration_type)
        if integration:
            await self.db.update(
                "workspace_integrations",
                integration["id"],
                {
                    "last_sync_at": datetime.now(timezone.utc),
                    "last_error": None,
                    "error_count": 0,
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

            await self.db.update(
                "workspace_integrations",
                integration["id"],
                {
                    "last_error": error,
                    "error_count": error_count,
                    "status": status,
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

        return await self.db.update(
            "workspace_integrations",
            integration["id"],
            {
                "status": IntegrationStatus.REVOKED.value,
                "access_token": None,
                "refresh_token": None,
            },
        )

    async def list_integrations(self) -> list[dict[str, Any]]:
        """
        List all integrations for the workspace.

        Returns:
            List of integration records
        """
        return await self.db.query_all(
            """
            SELECT * FROM workspace_integrations
            WHERE workspace_id = $1
            ORDER BY integration_type
            """,
            [self.workspace_id],
        )

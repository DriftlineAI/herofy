"""
OAuth State Manager (DataConnect Version)
Database-backed state management for CSRF protection using Firebase Data Connect.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from db.dataconnect_client import DataConnectClient
from core.logging import get_logger
from core.types import IntegrationType
from integrations.oauth.errors import OAuthStateError

logger = get_logger("StateManagerDC")


class StateManagerDC:
    """
    Manages OAuth state parameters with DataConnect persistence.

    State lifecycle:
    1. create_state() - Generate state, store in DB with expiry
    2. validate_state() - Verify state exists and hasn't expired/been consumed
    3. consume_state() - Mark state as consumed (one-time use)
    """

    def __init__(self, dc: DataConnectClient, state_ttl_minutes: int = 10):
        """
        Initialize StateManagerDC.

        Args:
            dc: DataConnect client
            state_ttl_minutes: How long states are valid (default 10 minutes)
        """
        self.dc = dc
        self.state_ttl_minutes = state_ttl_minutes

    async def create_state(
        self,
        workspace_id: str,
        user_id: str,
        integration_type: IntegrationType | str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> str:
        """
        Create a new OAuth state.

        Args:
            workspace_id: Workspace ID
            user_id: Firebase user UID
            integration_type: Type of integration
            redirect_uri: Callback URL
            code_verifier: PKCE code verifier (optional)

        Returns:
            Random state string (32 bytes URL-safe = 43 chars)
        """
        state = secrets.token_urlsafe(32)  # 256-bit entropy
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=self.state_ttl_minutes)

        if isinstance(integration_type, IntegrationType):
            integration_type = integration_type.value

        await self.dc.execute_mutation(
            "CreateOAuthState",
            {
                "state": state,
                "workspaceId": workspace_id,
                "integrationType": integration_type,
                "userId": user_id,
                "redirectUri": redirect_uri,
                "codeVerifier": code_verifier,
                "expiresAt": expires_at.isoformat(),
            },
        )

        logger.info(
            "oauth_state_created",
            workspace_id=workspace_id,
            integration_type=integration_type,
            expires_at=expires_at.isoformat(),
        )

        return state

    async def validate_state(self, state: str) -> dict[str, Any]:
        """
        Validate and return state record.

        Args:
            state: State string to validate

        Returns:
            State record dict

        Raises:
            OAuthStateError: If state is invalid, expired, or consumed
        """
        result = await self.dc.execute_query(
            "GetOAuthState",
            {"state": state},
        )

        states = result.get("oAuthStates", [])
        if not states:
            logger.warning("oauth_state_not_found", state_prefix=state[:8])
            raise OAuthStateError("Invalid OAuth state - not found")

        record = states[0]

        if record.get("consumed"):
            logger.warning("oauth_state_already_consumed", state_prefix=state[:8])
            raise OAuthStateError("OAuth state already consumed")

        expires_at = record.get("expiresAt")
        if expires_at:
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))

            if expires_at < datetime.now(timezone.utc):
                logger.warning("oauth_state_expired", state_prefix=state[:8])
                raise OAuthStateError("OAuth state expired")

        # Convert to legacy format for compatibility
        return self._to_legacy_format(record)

    def _to_legacy_format(self, record: dict[str, Any]) -> dict[str, Any]:
        """Convert GraphQL response to legacy SQL format."""
        return {
            "state": record.get("state"),
            "workspace_id": record.get("workspaceId"),
            "user_id": record.get("userId"),
            "integration_type": record.get("integrationType"),
            "redirect_uri": record.get("redirectUri"),
            "code_verifier": record.get("codeVerifier"),
            "expires_at": record.get("expiresAt"),
            "consumed": record.get("consumed"),
            "created_at": record.get("createdAt"),
        }

    async def consume_state(self, state: str) -> dict[str, Any]:
        """
        Atomically mark state as consumed and return the record.

        Args:
            state: State string

        Returns:
            State record dict

        Raises:
            OAuthStateError: If state is invalid, expired, or already consumed
        """
        # First validate
        record = await self.validate_state(state)

        # Then consume (mark as used)
        await self.dc.execute_mutation(
            "ConsumeOAuthState",
            {"state": state},
        )

        logger.info(
            "oauth_state_consumed",
            workspace_id=record["workspace_id"],
            integration_type=record["integration_type"],
        )

        record["consumed"] = True
        return record

    async def cleanup_expired(self) -> int:
        """
        Delete expired states (cleanup task).

        Returns:
            Number of states deleted (approximate, DataConnect doesn't return count)
        """
        now = datetime.now(timezone.utc).isoformat()

        await self.dc.execute_mutation(
            "DeleteExpiredOAuthStates",
            {"now": now},
        )

        logger.info("oauth_states_cleanup_executed")
        return 0  # DataConnect doesn't return affected count

"""
OAuth State Manager
Database-backed state management for CSRF protection.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from db.client import DatabaseClient
from core.logging import get_logger
from core.types import IntegrationType
from integrations.oauth.errors import OAuthStateError

logger = get_logger("StateManager")


class StateManager:
    """
    Manages OAuth state parameters with database persistence.

    State lifecycle:
    1. create_state() - Generate state, store in DB with expiry
    2. validate_state() - Verify state exists and hasn't expired/been consumed
    3. consume_state() - Mark state as consumed (one-time use)
    """

    def __init__(self, db: DatabaseClient, state_ttl_minutes: int = 10):
        """
        Initialize StateManager.

        Args:
            db: Database client
            state_ttl_minutes: How long states are valid (default 10 minutes)
        """
        self.db = db
        self.state_ttl_minutes = state_ttl_minutes

    async def create_state(
        self,
        workspace_id: str | UUID,
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

        created_at = datetime.now(timezone.utc)

        await self.db.execute(
            """
            INSERT INTO oauth_states (
                state, workspace_id, user_id, integration_type,
                redirect_uri, code_verifier, expires_at, consumed, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, false, $8)
            """,
            [
                state,
                str(workspace_id),
                user_id,
                integration_type,
                redirect_uri,
                code_verifier,
                expires_at,
                created_at,
            ],
        )

        logger.info(
            "oauth_state_created",
            workspace_id=str(workspace_id),
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
        record = await self.db.query_one(
            """
            SELECT * FROM oauth_states
            WHERE state = $1
            """,
            [state],
        )

        if not record:
            logger.warning("oauth_state_not_found", state_prefix=state[:8])
            raise OAuthStateError("Invalid OAuth state - not found")

        if record["consumed"]:
            logger.warning("oauth_state_already_consumed", state_prefix=state[:8])
            raise OAuthStateError("OAuth state already consumed")

        expires_at = record["expires_at"]
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))

        if expires_at < datetime.now(timezone.utc):
            logger.warning("oauth_state_expired", state_prefix=state[:8])
            raise OAuthStateError("OAuth state expired")

        return record

    async def consume_state(self, state: str) -> dict[str, Any]:
        """
        Atomically mark state as consumed and return the record.

        Uses UPDATE...RETURNING to prevent race conditions where the same
        state could be consumed twice.

        Args:
            state: State string

        Returns:
            State record dict

        Raises:
            OAuthStateError: If state is invalid, expired, or already consumed
        """
        # Atomic update - only updates if state exists, not consumed, and not expired
        record = await self.db.query_one(
            """
            UPDATE oauth_states
            SET consumed = true
            WHERE state = $1 AND consumed = false AND expires_at > $2
            RETURNING *
            """,
            [state, datetime.now(timezone.utc)],
        )

        if not record:
            # Could be: not found, already consumed, or expired
            # Log and raise generic error to avoid leaking state info
            logger.warning("oauth_state_consumption_failed", state_prefix=state[:8])
            raise OAuthStateError("Invalid, expired, or already used OAuth state")

        logger.info(
            "oauth_state_consumed",
            workspace_id=record["workspace_id"],
            integration_type=record["integration_type"],
        )

        return record

    async def cleanup_expired(self) -> int:
        """
        Delete expired states (cleanup task).

        Returns:
            Number of states deleted
        """
        result = await self.db.execute(
            """
            DELETE FROM oauth_states
            WHERE expires_at < $1 OR consumed = true
            """,
            [datetime.now(timezone.utc)],
        )

        # Parse "DELETE N" response
        count = int(result.split()[-1]) if result.startswith("DELETE") else 0

        if count > 0:
            logger.info("oauth_states_cleaned", deleted=count)

        return count

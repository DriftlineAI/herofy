"""
Event Emitter Base Class

Abstract interface for all event sources.
Replaces the old SignalSourceBase abstraction.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from core.logging import get_logger
from core.events import ChangeEvent, ChangeEventSource
from core.errors import (
    IntegrationNotConfiguredError,
    IntegrationTokenExpiredError,
    IntegrationAuthError,
)

logger = get_logger("EventEmitter")


class EventEmitterBase(ABC):
    """
    Abstract base class for event emitters.

    Event emitters poll external sources (Notion, Gmail, Slack) and
    produce ChangeEvent objects. The orchestrator collects these events
    and feeds them to SignalWatcher for processing.

    Implementations must provide:
    - poll_and_emit(): Fetch changes from source, return ChangeEvents
    - _get_source_type(): Return the ChangeEventSource enum value

    Watermark management is handled by the base class.

    Error Handling Contract:
    ------------------------
    All emitters MUST follow this error handling pattern in poll_and_emit():

    1. IntegrationNotConfiguredError → log info, return []
       (Integration not set up for this workspace - expected condition)

    2. IntegrationTokenExpiredError → log info, mark needs reconnection, return []
       (Token expired - user needs to re-authenticate)

    3. IntegrationAuthError → log info, mark needs reconnection, return []
       (Auth failed for other reasons - user needs to re-authenticate)

    4. Generic Exception → log error with full context, re-raise
       (Unexpected error - let orchestrator handle retry/alerting)

    This ensures consistent behavior across all emitters and allows
    the orchestrator to handle errors uniformly.
    """

    def __init__(self, workspace_id: str, db: Any = None):
        self.workspace_id = workspace_id
        # Note: db parameter kept for backward compatibility but no longer used
        self._watermark_key = f"event_emitter:{self._get_source_type().value}:watermark"

    @abstractmethod
    def _get_source_type(self) -> ChangeEventSource:
        """Return the event source type (notion, gmail, slack)."""
        pass

    @abstractmethod
    async def poll_and_emit(
        self,
        since: datetime | None = None,
    ) -> list[ChangeEvent]:
        """
        Poll source for changes and emit ChangeEvent objects.

        Args:
            since: Only fetch changes after this time. If None, uses stored watermark.

        Returns:
            List of ChangeEvent objects (not yet persisted - that's the orchestrator's job)
        """
        pass

    async def get_watermark(self) -> datetime | None:
        """
        Get the last successful poll timestamp.

        Returns:
            Last poll timestamp, or None if never polled
        """
        from db.dataconnect_client import get_dataconnect_client

        dc = get_dataconnect_client()
        result = await dc.execute_query(
            "GetAgentState",
            {
                "workspaceId": self.workspace_id,
                "key": self._watermark_key,
            },
        )

        states = result.get("agentStates", [])
        if states and states[0].get("value"):
            try:
                value = states[0]["value"]
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                logger.warning(
                    "invalid_watermark",
                    key=self._watermark_key,
                    value=states[0].get("value"),
                )
                return None
        return None

    async def update_watermark(self, timestamp: datetime) -> None:
        """
        Update the watermark after successful poll.

        Args:
            timestamp: New watermark timestamp
        """
        from db.dataconnect_client import get_dataconnect_client

        dc = get_dataconnect_client()
        await dc.execute_mutation(
            "UpsertAgentState",
            {
                "workspaceId": self.workspace_id,
                "key": self._watermark_key,
                "value": timestamp.isoformat(),
            },
        )

        logger.info(
            "watermark_updated",
            source=self._get_source_type().value,
            timestamp=timestamp.isoformat(),
        )

    async def get_integration_config(self) -> dict[str, Any] | None:
        """
        Get integration configuration from workspace_integrations.

        Returns:
            Config dict if integration is active, None otherwise
        """
        import json
        from db.dataconnect_client import get_dataconnect_client

        source_type = self._get_source_type().value

        dc = get_dataconnect_client()
        result = await dc.execute_query(
            "GetWorkspaceIntegrations",
            {"workspaceId": self.workspace_id},
        )

        # Find the matching integration
        for integration in result.get("workspaceIntegrations", []):
            if integration.get("integrationType") == source_type:
                if integration.get("status") != "active":
                    return None

                config = integration.get("config", {})
                if isinstance(config, str):
                    try:
                        config = json.loads(config)
                    except (json.JSONDecodeError, TypeError):
                        config = {}

                return config

        return None

    def _parse_email_domain(self, email: str | None) -> str | None:
        """Extract domain from email address."""
        if not email or "@" not in email:
            return None
        return email.split("@")[1].lower()

    async def _mark_needs_reconnection(self, reason: str = "Token expired") -> None:
        """
        Mark integration as needing reconnection.

        Sets integration status to 'error' with a message indicating
        the user needs to re-authenticate. This is visible in the UI.

        Args:
            reason: Human-readable reason for the reconnection requirement
        """
        from db.dataconnect_client import get_dataconnect_client

        source_type = self._get_source_type().value
        try:
            dc = get_dataconnect_client()
            await dc.execute_mutation(
                "MarkIntegrationNeedsReconnection",
                {
                    "workspaceId": self.workspace_id,
                    "integrationType": source_type,
                    "lastError": f"{reason} - reconnection required",
                },
            )
            logger.info(
                "integration_marked_needs_reconnection",
                workspace_id=self.workspace_id,
                source=source_type,
                reason=reason,
            )
        except Exception as e:
            logger.warning(
                "mark_reconnection_failed",
                workspace_id=self.workspace_id,
                source=source_type,
                error=str(e),
            )

    def _log_source_skipped(self, reason: str, error: str | None = None) -> None:
        """
        Log that this source was skipped (expected condition).

        Use for IntegrationNotConfiguredError, IntegrationTokenExpiredError,
        and IntegrationAuthError - not for unexpected errors.
        """
        log_kwargs = {
            "workspace_id": self.workspace_id,
            "source": self._get_source_type().value,
            "reason": reason,
        }
        if error:
            log_kwargs["error"] = error

        logger.info("source_skipped", **log_kwargs)

    def _log_poll_failed(self, error: str) -> None:
        """
        Log that polling failed unexpectedly.

        Use for generic exceptions that will be re-raised.
        """
        logger.error(
            "poll_failed",
            workspace_id=self.workspace_id,
            source=self._get_source_type().value,
            error=error,
        )

    # =============================================================================
    # Customer Resolution (Shared by Gmail and Slack)
    # =============================================================================

    async def _resolve_customer(
        self,
        sender_email: str,
        sender_domain: str | None,
        sender_name: str,
    ):
        """
        Customer resolution cascade (shared by Gmail and Slack emitters).

        Resolution steps:
        1. Exact stakeholder email match
        2. Domain match (skips personal domains like gmail.com)
        3. Returns None if no match (unknown_sender)

        If domain matches, auto-creates stakeholder record for the customer.

        Args:
            sender_email: Email address
            sender_domain: Email domain (already extracted)
            sender_name: Display name

        Returns:
            Customer UUID or None
        """
        from uuid import UUID
        from db.dataconnect_client import get_dataconnect_client
        from core.events import is_personal_email_domain

        if not sender_email:
            return None

        dc = get_dataconnect_client()

        # Step 1: Exact stakeholder email match
        stakeholder_result = await dc.execute_query(
            "GetStakeholderByEmail",
            {
                "workspaceId": self.workspace_id,
                "email": sender_email.lower(),
            },
        )

        stakeholders = stakeholder_result.get("stakeholders", [])
        if stakeholders:
            customer = stakeholders[0].get("customer", {})
            if customer and customer.get("id"):
                return UUID(str(customer["id"]))

        # Step 2: Domain match (skip personal email domains)
        if sender_domain and not is_personal_email_domain(sender_domain):
            customer_result = await dc.execute_query(
                "GetCustomerByDomain",
                {
                    "workspaceId": self.workspace_id,
                    "domain": sender_domain.lower(),
                },
            )

            customers = customer_result.get("customers", [])
            if customers:
                customer_id = UUID(str(customers[0]["id"]))

                # Auto-create stakeholder for this customer
                await self._create_stakeholder(customer_id, sender_email, sender_name)

                return customer_id

        # Step 3: No match
        return None

    async def _create_stakeholder(
        self,
        customer_id,
        email: str,
        name: str,
    ) -> None:
        """
        Auto-create a stakeholder record when domain matching succeeds.

        Idempotent: uses upsert to skip if stakeholder already exists.

        Args:
            customer_id: Customer UUID
            email: Stakeholder email
            name: Stakeholder display name
        """
        from db.dataconnect_client import get_dataconnect_client

        try:
            dc = get_dataconnect_client()

            # Upsert stakeholder (will skip if email already exists for this customer)
            import uuid
            await dc.execute_mutation(
                "CreateStakeholderIfNotExists",
                {
                    "id": str(uuid.uuid4()),
                    "workspaceId": self.workspace_id,
                    "customerId": str(customer_id),
                    "name": name or email.split("@")[0],
                    "email": email.lower(),
                },
            )

            logger.info(
                "stakeholder_auto_created",
                workspace_id=self.workspace_id,
                customer_id=str(customer_id),
                email=email,
            )

        except Exception as e:
            logger.warning(
                "stakeholder_creation_failed",
                workspace_id=self.workspace_id,
                email=email,
                error=str(e),
            )

"""
Gmail Event Emitter

Polls Gmail for new messages and emits ChangeEvents.
Replaces the old GmailSignalSource class entirely.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from core.logging import get_logger
from core.errors import (
    IntegrationNotConfiguredError,
    IntegrationTokenExpiredError,
    IntegrationAuthError,
)
from core.events import (
    ChangeEvent,
    ChangeEventSource,
    MessagePayload,
    is_personal_email_domain,
)
from services.integration_service_dc import IntegrationServiceDC
from integrations.clients.gmail_client import GmailClient

from .base import EventEmitterBase

logger = get_logger("GmailEmitter")


class GmailEventEmitter(EventEmitterBase):
    """
    Gmail event emitter - replaces GmailSignalSource.

    Fetches emails from Gmail API and converts them to ChangeEvent objects.
    Customer resolution cascade:
    1. Exact stakeholder email match
    2. Domain match against customer domains (with personal domain blocklist)
    3. If both fail → unknown_sender

    When domain match succeeds, auto-creates a stakeholder record.
    """

    def __init__(
        self,
        workspace_id: str,
        db: Any = None,  # Kept for backward compatibility but unused
        integration_service: IntegrationServiceDC | None = None,
    ):
        super().__init__(workspace_id, db)

        if integration_service is None:
            from db.dataconnect_client import get_dataconnect_client
            dc = get_dataconnect_client()
            integration_service = IntegrationServiceDC(dc, workspace_id)
        self.integration_service = integration_service
        self._gmail_client: GmailClient | None = None

    @property
    def gmail_client(self) -> GmailClient:
        """Get or create Gmail client (lazy initialization)."""
        if self._gmail_client is None:
            self._gmail_client = GmailClient(self.integration_service)
        return self._gmail_client

    def _get_source_type(self) -> ChangeEventSource:
        return ChangeEventSource.GMAIL

    async def poll_and_emit(
        self,
        since: datetime | None = None,
    ) -> list[ChangeEvent]:
        """
        Fetch new messages from Gmail since the given timestamp.

        Args:
            since: Only fetch emails after this time. If None, uses watermark or 24h ago.

        Returns:
            List of ChangeEvent objects
        """
        try:
            # Get watermark if not provided
            if since is None:
                since = await self.get_watermark()

            # Default to last 24 hours if no watermark
            if since is None:
                since = datetime.now(timezone.utc) - timedelta(hours=24)

            # Ensure timezone awareness
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)

            # Fetch messages from Gmail
            messages = await self.gmail_client.list_messages_since(
                since=since,
                max_results=100,
            )

            # Convert to ChangeEvent format
            events: list[ChangeEvent] = []
            for msg in messages:
                event = await self.convert_gmail_message_to_event(msg)
                if event:
                    events.append(event)

            logger.info(
                "gmail_events_emitted",
                workspace_id=self.workspace_id,
                count=len(events),
                since=since.isoformat(),
            )

            return events

        except IntegrationNotConfiguredError:
            self._log_source_skipped("not_configured")
            return []

        except IntegrationTokenExpiredError:
            self._log_source_skipped("token_expired")
            await self._mark_needs_reconnection("Token expired")
            return []

        except IntegrationAuthError as e:
            self._log_source_skipped("auth_failed", str(e))
            await self._mark_needs_reconnection("Auth failed")
            return []

        except Exception as e:
            self._log_poll_failed(str(e))
            raise

    async def convert_gmail_message_to_event(
        self, message: dict[str, Any]
    ) -> ChangeEvent | None:
        """
        Convert a Gmail message to a ChangeEvent.

        PUBLIC METHOD - Called from:
        - Webhook handler (push notifications)
        - poll_and_emit() (fallback polling)

        Includes customer resolution cascade:
        1. Exact stakeholder email match
        2. Domain match (skips personal domains like gmail.com)
        3. Returns None (unknown_sender) → ChangeEvent with customer_id=None
        """
        sender_email = message.get("from", "")
        sender_name = sender_email

        # Parse sender name and email from "Name <email>" format
        if "<" in sender_email and ">" in sender_email:
            parts = sender_email.split("<")
            sender_name = parts[0].strip().strip('"')
            sender_email = parts[1].rstrip(">").strip()

        # Extract domain
        sender_domain = self._parse_email_domain(sender_email)

        # Skip internal/system emails
        if self._should_skip_email(sender_email, sender_domain):
            return None

        # Parse timestamp from internal_date (milliseconds since epoch)
        occurred_at = datetime.now(timezone.utc)
        if message.get("internal_date"):
            try:
                ts_ms = int(message["internal_date"])
                occurred_at = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            except (ValueError, TypeError):
                pass

        # Customer resolution cascade
        customer_id = await self._resolve_customer(sender_email, sender_domain, sender_name)

        # Compute fingerprint
        message_id = message.get("id", "")
        fingerprint = ChangeEvent.compute_fingerprint(
            "gmail",
            message_id,
            "",  # No content hash needed - message_id is unique
        )

        payload = MessagePayload(
            sender_email=sender_email,
            sender_name=sender_name,
            sender_domain=sender_domain,
            subject=message.get("subject"),
            body=message.get("body", ""),
            channel="email",
            reply_to_id=message.get("thread_id"),  # Use thread_id for conversation tracking
            thread_id=message.get("thread_id"),
        )

        return ChangeEvent(
            id=uuid4(),
            workspace_id=UUID(self.workspace_id),
            source=ChangeEventSource.GMAIL,
            source_event_type="gmail_message",
            source_record_id=message_id,
            fingerprint=fingerprint,
            customer_id=customer_id,
            raw_payload={
                **payload.model_dump(),
                "gmail_id": message.get("id"),
                "label_ids": message.get("label_ids", []),
                "snippet": message.get("snippet"),
            },
            occurred_at=occurred_at,
        )

    # Note: _resolve_customer() and _create_stakeholder() are inherited from EventEmitterBase

    def _should_skip_email(self, email: str, domain: str | None) -> bool:
        """
        Determine if an email should be skipped (internal/system).
        """
        if not email:
            return True

        # Skip common system/notification addresses
        skip_patterns = [
            "noreply@",
            "no-reply@",
            "mailer-daemon@",
            "postmaster@",
            "notifications@",
            "alerts@",
            "donotreply@",
            "do-not-reply@",
        ]

        email_lower = email.lower()
        for pattern in skip_patterns:
            if pattern in email_lower:
                return True

        # Skip common service domains
        skip_domains = {
            "google.com",
            "googlemail.com",
            "github.com",
            "linkedin.com",
            "twitter.com",
            "facebook.com",
            "stripe.com",
            "intercom.io",
            "zendesk.com",
            "mailchimp.com",
            "sendgrid.net",
            "calendly.com",
            "hubspot.com",
            "salesforce.com",
            "atlassian.net",
        }

        if domain and domain.lower() in skip_domains:
            return True

        return False


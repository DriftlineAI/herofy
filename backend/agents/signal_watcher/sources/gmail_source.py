"""
Gmail Signal Source
Real Gmail signal source using GmailClient for fetching customer emails.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from core.logging import get_logger
from core.errors import (
    IntegrationNotConfiguredError,
    IntegrationTokenExpiredError,
    IntegrationAuthError,
)
from core.types import IntegrationType
from services.integration_service import IntegrationService
from integrations.clients.gmail_client import GmailClient

from ..models import RawSignal, SignalSource
from .base import SignalSourceBase

logger = get_logger("GmailSignalSource")


class GmailSignalSource(SignalSourceBase):
    """
    Real Gmail signal source using GmailClient.

    Fetches emails from Gmail API and converts them to RawSignal format
    for processing by the SignalWatcher pipeline.
    """

    def __init__(
        self,
        workspace_id: str,
        integration_service: IntegrationService,
    ):
        """
        Initialize Gmail signal source.

        Args:
            workspace_id: Workspace ID for this source
            integration_service: Service for getting valid OAuth tokens
        """
        super().__init__(workspace_id)
        self.integration_service = integration_service
        self._gmail_client: GmailClient | None = None

    @property
    def gmail_client(self) -> GmailClient:
        """Get or create Gmail client (lazy initialization)."""
        if self._gmail_client is None:
            self._gmail_client = GmailClient(self.integration_service)
        return self._gmail_client

    def _get_source_type(self) -> SignalSource:
        return SignalSource.GMAIL

    async def fetch_signals(self, since: datetime | None = None) -> list[RawSignal]:
        """
        Fetch new signals from Gmail since the given timestamp.

        Args:
            since: Only fetch emails after this time. If None, fetches from 24h ago.

        Returns:
            List of RawSignal objects from Gmail
        """
        try:
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

            # Convert to RawSignal format
            signals: list[RawSignal] = []
            for msg in messages:
                signal = self._message_to_signal(msg)
                if signal:
                    signals.append(signal)

            logger.info(
                "gmail_signals_fetched",
                workspace_id=self.workspace_id,
                count=len(signals),
                since=since.isoformat(),
            )

            return signals

        except IntegrationNotConfiguredError:
            logger.info(
                "source_skipped",
                workspace_id=self.workspace_id,
                source=self._get_source_type().value,
                reason="not_configured",
            )
            return []

        except IntegrationTokenExpiredError:
            logger.info(
                "source_skipped",
                workspace_id=self.workspace_id,
                source=self._get_source_type().value,
                reason="token_expired_needs_reconnection",
            )
            await self._mark_needs_reconnection("Token expired")
            return []

        except IntegrationAuthError as e:
            logger.info(
                "source_skipped",
                workspace_id=self.workspace_id,
                source=self._get_source_type().value,
                reason="auth_failed_needs_reconnection",
                error=str(e),
            )
            await self._mark_needs_reconnection("Auth failed")
            return []

        except Exception as e:
            logger.error(
                "gmail_fetch_failed",
                workspace_id=self.workspace_id,
                error=str(e),
            )
            raise

    def _message_to_signal(self, message: dict[str, Any]) -> RawSignal | None:
        """
        Convert a Gmail message to a RawSignal.

        Args:
            message: Parsed Gmail message from GmailClient

        Returns:
            RawSignal or None if message should be skipped
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

        return RawSignal(
            id=str(uuid4()),
            source=SignalSource.GMAIL,
            external_id=message.get("id", ""),
            sender_email=sender_email,
            sender_name=sender_name,
            sender_domain=sender_domain,
            subject=message.get("subject"),
            body=message.get("body", ""),
            channel="email",
            reply_to_id=message.get("thread_id"),  # Use thread_id for conversation tracking
            thread_id=message.get("thread_id"),
            occurred_at=occurred_at,
            raw_metadata={
                "gmail_id": message.get("id"),
                "thread_id": message.get("thread_id"),
                "label_ids": message.get("label_ids", []),
                "snippet": message.get("snippet"),
            },
        )

    def _should_skip_email(self, email: str, domain: str | None) -> bool:
        """
        Determine if an email should be skipped (internal/system).

        Args:
            email: Sender email address
            domain: Sender domain

        Returns:
            True if email should be skipped
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
        }

        if domain and domain.lower() in skip_domains:
            return True

        return False

    async def _mark_needs_reconnection(self, reason: str = "Token expired") -> None:
        """
        Mark integration as needing reconnection (visible in UI).

        Idempotent: skips write if already marked as error within last hour.
        """
        try:
            # Check existing status first
            result = await self.dc.execute_query(
                "GetWorkspaceIntegration",
                {
                    "workspaceId": self.workspace_id,
                    "integrationType": IntegrationType.GMAIL.value,
                },
            )

            integration = result.get("workspaceIntegration")
            if integration:
                updated_at = integration.get("updatedAt")
                if isinstance(updated_at, str):
                    updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                elif updated_at and updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)

                is_recent_error = (
                    integration["status"] == "error"
                    and updated_at
                    and updated_at > datetime.now(timezone.utc) - timedelta(hours=1)
                )
                if is_recent_error:
                    logger.debug(
                        "reconnection_already_marked",
                        workspace_id=self.workspace_id,
                        source=self._get_source_type().value,
                    )
                    return

            # Mark as needing reconnection using DataConnect
            await self.dc.execute_mutation(
                "MarkIntegrationNeedsReconnection",
                {
                    "workspaceId": self.workspace_id,
                    "integrationType": IntegrationType.GMAIL.value,
                    "errorMessage": f"{reason} - reconnection required",
                },
            )
        except Exception as e:
            logger.warning(
                "mark_reconnection_failed",
                workspace_id=self.workspace_id,
                error=str(e),
            )

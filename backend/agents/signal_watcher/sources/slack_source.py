"""
Slack Signal Source
Real Slack signal source using SlackClient for fetching customer messages.
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
from integrations.clients.slack_client import SlackClient, SlackAPIError

from ..models import RawSignal, SignalSource
from .base import SignalSourceBase

logger = get_logger("SlackSignalSource")


class SlackSignalSource(SignalSourceBase):
    """
    Real Slack signal source using SlackClient.

    Fetches messages from Slack channels the bot is a member of and converts
    them to RawSignal format for processing by the SignalWatcher pipeline.
    """

    def __init__(
        self,
        workspace_id: str,
        integration_service: IntegrationService,
    ):
        """
        Initialize Slack signal source.

        Args:
            workspace_id: Workspace ID for this source
            integration_service: Service for getting valid OAuth tokens
        """
        super().__init__(workspace_id)
        self.integration_service = integration_service
        self._slack_client: SlackClient | None = None
        self._user_cache: dict[str, dict[str, Any]] = {}

    @property
    def slack_client(self) -> SlackClient:
        """Get or create Slack client (lazy initialization)."""
        if self._slack_client is None:
            self._slack_client = SlackClient(self.integration_service)
        return self._slack_client

    def _get_source_type(self) -> SignalSource:
        return SignalSource.SLACK

    async def fetch_signals(self, since: datetime | None = None) -> list[RawSignal]:
        """
        Fetch new signals from Slack since the given timestamp.

        Args:
            since: Only fetch messages after this time. If None, fetches from 24h ago.

        Returns:
            List of RawSignal objects from Slack
        """
        try:
            # Default to last 24 hours if no watermark
            if since is None:
                since = datetime.now(timezone.utc) - timedelta(hours=24)

            # Ensure timezone awareness
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)

            # Convert to Slack timestamp format (Unix epoch as string)
            oldest = str(since.timestamp())

            # Get channels the bot is a member of
            channels_result = await self.slack_client.list_channels(limit=100)
            channels = channels_result.get("channels", [])

            signals: list[RawSignal] = []

            # Fetch history from each channel
            for channel in channels:
                channel_id = channel.get("id")
                channel_name = channel.get("name", "unknown")

                try:
                    history = await self.slack_client.get_channel_history(
                        channel=channel_id,
                        oldest=oldest,
                        limit=100,
                    )

                    messages = history.get("messages", [])

                    for msg in messages:
                        signal = await self._message_to_signal(
                            msg, channel_id, channel_name
                        )
                        if signal:
                            signals.append(signal)

                except SlackAPIError as e:
                    # Skip channels we can't access
                    logger.warning(
                        "slack_channel_fetch_failed",
                        channel_id=channel_id,
                        channel_name=channel_name,
                        error=str(e),
                    )
                    continue

            logger.info(
                "slack_signals_fetched",
                workspace_id=self.workspace_id,
                count=len(signals),
                channels_checked=len(channels),
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
                "slack_fetch_failed",
                workspace_id=self.workspace_id,
                error=str(e),
            )
            raise

    async def _message_to_signal(
        self,
        message: dict[str, Any],
        channel_id: str,
        channel_name: str,
    ) -> RawSignal | None:
        """
        Convert a Slack message to a RawSignal.

        Args:
            message: Slack message object
            channel_id: Channel ID
            channel_name: Channel name

        Returns:
            RawSignal or None if message should be skipped
        """
        # Skip bot messages and system messages
        if message.get("subtype") in ("bot_message", "channel_join", "channel_leave"):
            return None

        user_id = message.get("user")
        if not user_id:
            return None

        # Get user info (cached)
        user_info = await self._get_user_info(user_id)
        if not user_info:
            return None

        # Skip bot users
        if user_info.get("is_bot"):
            return None

        # Extract user details
        profile = user_info.get("profile", {})
        sender_email = profile.get("email", "")
        sender_name = user_info.get("real_name") or profile.get("display_name", user_id)
        sender_domain = self._parse_email_domain(sender_email)

        # Parse timestamp
        ts = message.get("ts", "")
        occurred_at = datetime.now(timezone.utc)
        if ts:
            try:
                occurred_at = datetime.fromtimestamp(float(ts), tz=timezone.utc)
            except (ValueError, TypeError):
                pass

        # Get thread info
        thread_ts = message.get("thread_ts")
        reply_to_id = thread_ts if thread_ts and thread_ts != ts else None

        # Build message body
        body = message.get("text", "")

        # Extract subject from channel context
        subject = f"Message in #{channel_name}"

        return RawSignal(
            id=str(uuid4()),
            source=SignalSource.SLACK,
            external_id=ts,
            sender_email=sender_email,
            sender_name=sender_name,
            sender_domain=sender_domain,
            subject=subject,
            body=body,
            channel="slack",
            reply_to_id=reply_to_id,
            thread_id=thread_ts,
            occurred_at=occurred_at,
            raw_metadata={
                "slack_ts": ts,
                "channel_id": channel_id,
                "channel_name": channel_name,
                "thread_ts": thread_ts,
                "user_id": user_id,
                "reactions": message.get("reactions", []),
            },
        )

    async def _get_user_info(self, user_id: str) -> dict[str, Any] | None:
        """
        Get user info from cache or Slack API.

        Args:
            user_id: Slack user ID

        Returns:
            User info dict or None
        """
        if user_id in self._user_cache:
            return self._user_cache[user_id]

        try:
            user_info = await self.slack_client.get_user_info(user_id)
            self._user_cache[user_id] = user_info
            return user_info
        except SlackAPIError as e:
            logger.warning(
                "slack_user_fetch_failed",
                user_id=user_id,
                error=str(e),
            )
            return None

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
                    "integrationType": IntegrationType.SLACK.value,
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
                    "integrationType": IntegrationType.SLACK.value,
                    "errorMessage": f"{reason} - reconnection required",
                },
            )
        except Exception as e:
            logger.warning(
                "mark_reconnection_failed",
                workspace_id=self.workspace_id,
                error=str(e),
            )

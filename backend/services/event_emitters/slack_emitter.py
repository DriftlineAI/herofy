"""
Slack Event Emitter

Polls Slack for new messages and emits ChangeEvents.
Replaces the old SlackSignalSource class entirely.
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
from integrations.clients.slack_client import SlackClient, SlackAPIError

from .base import EventEmitterBase

logger = get_logger("SlackEmitter")


class SlackEventEmitter(EventEmitterBase):
    """
    Slack event emitter - replaces SlackSignalSource.

    Fetches messages from Slack channels and converts them to ChangeEvent objects.
    Uses same customer resolution cascade as Gmail:
    1. Exact stakeholder email match
    2. Domain match against customer domains (with personal domain blocklist)
    3. If both fail → unknown_sender
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
        self._slack_client: SlackClient | None = None
        # Bounded cache to prevent memory leaks - max 500 users per poll cycle
        self._user_cache: dict[str, dict[str, Any]] = {}
        self._user_cache_max_size = 500

    @property
    def slack_client(self) -> SlackClient:
        """Get or create Slack client (lazy initialization)."""
        if self._slack_client is None:
            self._slack_client = SlackClient(self.integration_service)
        return self._slack_client

    def _get_source_type(self) -> ChangeEventSource:
        return ChangeEventSource.SLACK

    async def poll_and_emit(
        self,
        since: datetime | None = None,
    ) -> list[ChangeEvent]:
        """
        Fetch new messages from Slack since the given timestamp.

        Args:
            since: Only fetch messages after this time. If None, uses watermark or 24h ago.

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

            # Convert to Slack timestamp format (Unix epoch as string)
            oldest = str(since.timestamp())

            # Get channels the bot is a member of
            channels_result = await self.slack_client.list_channels(limit=100)
            channels = channels_result.get("channels", [])

            events: list[ChangeEvent] = []

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
                        event = await self.convert_slack_message_to_event(
                            msg, channel_id, channel_name
                        )
                        if event:
                            events.append(event)

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
                "slack_events_emitted",
                workspace_id=self.workspace_id,
                count=len(events),
                channels_checked=len(channels),
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

    async def convert_slack_message_to_event(
        self,
        message: dict[str, Any],
        channel_id: str,
        channel_name: str,
    ) -> ChangeEvent | None:
        """
        Convert a Slack message to a ChangeEvent.

        PUBLIC METHOD - Called from:
        - Bolt event handlers (webhook/Socket Mode)
        - poll_and_emit() (backfill polling)

        Args:
            message: Slack message object
            channel_id: Channel ID
            channel_name: Channel name (or "unknown")

        Returns:
            ChangeEvent or None if message should be skipped

        Includes customer resolution cascade:
        1. Exact stakeholder email match
        2. Domain match (skips personal domains like gmail.com)
        3. Returns None (unknown_sender) → no ChangeEvent created
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

        # Customer resolution cascade
        customer_id = await self._resolve_customer(sender_email, sender_domain, sender_name)

        # Compute fingerprint using Slack timestamp (unique per channel)
        fingerprint = ChangeEvent.compute_fingerprint(
            "slack",
            f"{channel_id}:{ts}",
            "",
        )

        payload = MessagePayload(
            sender_email=sender_email,
            sender_name=sender_name,
            sender_domain=sender_domain,
            subject=subject,
            body=body,
            channel="slack",
            reply_to_id=reply_to_id,
            thread_id=thread_ts,
        )

        return ChangeEvent(
            id=uuid4(),
            workspace_id=UUID(self.workspace_id),
            source=ChangeEventSource.SLACK,
            source_event_type="slack_message",
            source_record_id=f"{channel_id}:{ts}",
            fingerprint=fingerprint,
            customer_id=customer_id,
            raw_payload={
                **payload.model_dump(),
                "slack_ts": ts,
                "channel_id": channel_id,
                "channel_name": channel_name,
                "thread_ts": thread_ts,
                "user_id": user_id,
                "reactions": message.get("reactions", []),
            },
            occurred_at=occurred_at,
        )

    # Note: _resolve_customer() and _create_stakeholder() are inherited from EventEmitterBase

    async def _get_user_info(self, user_id: str) -> dict[str, Any] | None:
        """
        Get user info from cache or Slack API.

        Cache is bounded to prevent memory leaks in long-running processes.
        """
        if user_id in self._user_cache:
            return self._user_cache[user_id]

        try:
            user_info = await self.slack_client.get_user_info(user_id)

            # Evict oldest entries if cache is full (simple FIFO eviction)
            if len(self._user_cache) >= self._user_cache_max_size:
                # Remove first entry (oldest) - dict maintains insertion order in Python 3.7+
                oldest_key = next(iter(self._user_cache))
                del self._user_cache[oldest_key]

            self._user_cache[user_id] = user_info
            return user_info
        except SlackAPIError as e:
            logger.warning(
                "slack_user_fetch_failed",
                user_id=user_id,
                error=str(e),
            )
            return None

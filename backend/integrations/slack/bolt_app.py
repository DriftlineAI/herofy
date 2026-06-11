"""
Slack Bolt Application
Handles Slack event processing via Bolt for Python SDK
"""

import asyncio
from typing import Any
from uuid import UUID

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler

from core.logging import get_logger
from core.events import ChangeEvent

logger = get_logger("SlackBolt")

# Global Bolt app instance (lazy-initialized)
_bolt_app: AsyncApp | None = None

# Background task tracking (prevents GC, enables graceful shutdown)
_background_tasks: set[asyncio.Task] = set()


def get_bolt_app() -> AsyncApp:
    """
    Get or create the Bolt app instance.

    Lazy initialization to avoid loading config at import time.
    """
    global _bolt_app
    if _bolt_app is None:
        from config import settings

        _bolt_app = AsyncApp(
            token=settings.slack_bot_token,
            signing_secret=settings.slack_signing_secret,
        )
        _register_handlers(_bolt_app)
        logger.info("Bolt app initialized")

    return _bolt_app


def get_slack_handler() -> AsyncSlackRequestHandler:
    """
    Get FastAPI adapter for production webhook mode.

    Returns:
        AsyncSlackRequestHandler for mounting at /slack/events
    """
    app = get_bolt_app()
    return AsyncSlackRequestHandler(app)


def get_background_tasks() -> set[asyncio.Task]:
    """
    Get the set of in-flight background tasks.

    Used by lifespan shutdown to wait for tasks to complete.
    """
    return _background_tasks


# =============================================================================
# Background Task Management
# =============================================================================


async def _process_event_safely(workspace_id: str, event: ChangeEvent):
    """
    Wrapper for _persist_and_process_event with exception handling.

    Ensures exceptions in background tasks are logged (not silently dropped).
    """
    try:
        await _persist_and_process_event(workspace_id, event)
    except Exception as e:
        logger.exception(
            "background_event_processing_failed",
            workspace_id=workspace_id,
            event_id=str(event.id),
            error=str(e),
        )


def _fire_and_forget(coro):
    """
    Schedule a coroutine as a background task with proper lifecycle management.

    Addresses three fire-and-forget footguns:
    1. Holds task reference to prevent GC mid-execution
    2. Logs unobserved exceptions via _process_event_safely wrapper
    3. Enables graceful shutdown via _background_tasks tracking

    Args:
        coro: Coroutine to run in background
    """
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


# =============================================================================
# Event Handlers
# =============================================================================


def _register_handlers(app: AsyncApp):
    """Register all Bolt event handlers."""

    @app.message()
    async def handle_message(message: dict[str, Any], context: dict[str, Any]):
        """
        Handle all message events from channels and groups.

        Filters:
        - Skip bot messages (subtype="bot_message")
        - Skip system messages (channel_join, channel_leave)
        - Skip messages with bot_id (other bots)

        Does NOT filter:
        - Thread replies (genuinely meaningful in customer channels)
        - Specific channels (let SignalWatcher classify)
        """
        # Filter: skip bot messages
        if message.get("subtype") in ("bot_message", "channel_join", "channel_leave"):
            return

        if message.get("bot_id"):
            logger.debug("skipping_bot_message", bot_id=message.get("bot_id"))
            return

        # Get workspace_id from Slack team_id
        team_id = context.get("team_id")
        if not team_id:
            logger.info("slack_event_skipped", reason="no_team_id")
            return

        workspace_id = await _lookup_workspace_by_team_id(team_id)
        if not workspace_id:
            logger.info("slack_event_skipped", reason="workspace_not_found", team_id=team_id)
            return

        # Get channel info
        channel_id = message.get("channel")
        channel_type = message.get("channel_type", "channel")  # "channel", "group", "im", "mpim"

        # Build channel name (Bolt doesn't provide it in message event)
        # For now, use channel_id. Future: cache channel names or fetch from API
        channel_name = channel_id or "unknown"

        # Convert message to ChangeEvent
        from services.event_emitters.slack_emitter import SlackEventEmitter

        emitter = SlackEventEmitter(workspace_id)
        event = await emitter.convert_slack_message_to_event(
            message=message,
            channel_id=channel_id,
            channel_name=channel_name,
        )

        if not event:
            logger.debug("Message filtered by emitter")
            return

        # Fire-and-forget: Process in background, return 200 to Slack immediately
        # Avoids timeout on slow SignalWatcher cascade (LLM classification, fan-out)
        _fire_and_forget(_process_event_safely(workspace_id, event))

        logger.info(
            "message_queued_for_processing",
            workspace_id=workspace_id,
            channel_id=channel_id,
            channel_type=channel_type,
            event_id=str(event.id),
        )

    @app.event("member_joined_channel")
    async def handle_member_joined(event: dict[str, Any]):
        """
        Handle member_joined_channel events.

        Future: Track for signal "new stakeholder joined customer channel"
        """
        user_id = event.get("user")
        channel_id = event.get("channel")

        logger.info(
            "member_joined_channel",
            user=user_id,
            channel=channel_id,
        )
        # Future: create ChangeEvent for member join events

    @app.event("member_left_channel")
    async def handle_member_left(event: dict[str, Any]):
        """
        Handle member_left_channel events.

        Future: Track for signal "stakeholder departed"
        """
        user_id = event.get("user")
        channel_id = event.get("channel")

        logger.info(
            "member_left_channel",
            user=user_id,
            channel=channel_id,
        )
        # Future: create ChangeEvent for member departure events


# =============================================================================
# Helper Functions
# =============================================================================


async def _lookup_workspace_by_team_id(team_id: str) -> str | None:
    """
    Look up Herofy workspace_id by Slack team_id.

    Args:
        team_id: Slack team/workspace ID

    Returns:
        Workspace ID or None if not found
    """
    from db.dataconnect_client import get_dataconnect_client

    try:
        dc = get_dataconnect_client()
        result = await dc.execute_query(
            "GetWorkspaceBySlackTeamId",
            {"slackTeamId": team_id},
        )

        integrations = result.get("workspaceIntegrations", [])
        if integrations:
            workspace = integrations[0].get("workspace", {})
            return workspace.get("id")

        return None

    except Exception as e:
        logger.exception("workspace_lookup_failed", team_id=team_id, error=str(e))
        return None


async def _persist_and_process_event(workspace_id: str, event: ChangeEvent):
    """
    Persist ChangeEvent to database and trigger processing.

    Args:
        workspace_id: Workspace ID
        event: ChangeEvent to persist
    """
    from db.dataconnect_client import get_dataconnect_client
    from agents.signal_watcher_unified.event_processor import SignalWatcherEventProcessor

    try:
        dc = get_dataconnect_client()

        # Persist event (dedup by fingerprint)
        db_event_id: str | None = None
        try:
            result = await dc.execute_mutation(
                "CreateChangeEvent",
                {
                    "workspaceId": workspace_id,
                    "source": event.source.value,
                    "sourceEventType": event.source_event_type,
                    "sourceRecordId": event.source_record_id,
                    "fingerprint": event.fingerprint,
                    "customerId": str(event.customer_id) if event.customer_id else None,
                    "rawPayload": event.raw_payload_json,
                    "occurredAt": event.occurred_at.isoformat(),
                },
            )
            db_event_id = (result.get("changeEvent_insert") or {}).get("id")
            logger.debug("event_persisted", fingerprint=event.fingerprint, db_event_id=db_event_id)

        except Exception as e:
            # Duplicate fingerprint is expected (idempotent webhook retries)
            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                logger.debug("event_duplicate_skipped", fingerprint=event.fingerprint)
                return
            raise

        # Process event through SignalWatcher pipeline
        processor = SignalWatcherEventProcessor(workspace_id)
        processed_events = await processor.process_events([event])

        logger.info(
            "event_processed",
            workspace_id=workspace_id,
            db_event_id=db_event_id,
            fingerprint=event.fingerprint,
            artifacts_count=len(processed_events[0].artifacts_created) if processed_events else 0,
        )

    except Exception as e:
        logger.exception(
            "event_processing_failed",
            workspace_id=workspace_id,
            fingerprint=event.fingerprint,
            error=str(e),
        )
        # Update event with processing error (don't re-raise - return 200 to Slack)
        try:
            if db_event_id:
                await dc.execute_mutation(
                    "MarkChangeEventError",
                    {
                        "eventId": db_event_id,
                        "error": str(e),
                    },
                )
        except Exception as mark_error_exc:
            logger.warning(
                "failed_to_record_processing_error",
                fingerprint=event.fingerprint,
                original_error=str(e),
                mark_error_exception=str(mark_error_exc),
            )

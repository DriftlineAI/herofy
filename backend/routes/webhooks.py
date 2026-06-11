"""
Webhook Routes
Receives webhooks from external integrations (Gmail, Slack, Calendar, Notion)
and triggers signal processing.
"""

import hashlib
import hmac
import json
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Header, BackgroundTasks
from pydantic import BaseModel

from core.logging import get_logger
from config import settings

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = get_logger("webhooks")


# =============================================================================
# Webhook Verification Helpers
# =============================================================================


def verify_google_pubsub_token(token: str) -> bool:
    """Verify Google Pub/Sub push token."""
    if not settings.google_pubsub_token:
        # No token configured - allow in development
        return settings.is_development

    return hmac.compare_digest(token, settings.google_pubsub_token)


# =============================================================================
# Gmail Webhook (via Google Pub/Sub)
# =============================================================================


class GmailPubSubMessage(BaseModel):
    """Google Pub/Sub push message format."""
    message: dict
    subscription: str


@router.post("/gmail")
async def gmail_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(None),
):
    """
    Receive Gmail notifications via Google Pub/Sub.

    Google Pub/Sub pushes notifications when there are changes to Gmail.
    We fetch the actual email content using the Gmail API and process it.

    Flow:
    1. Verify Pub/Sub token
    2. Decode base64 message (contains: emailAddress, historyId)
    3. Look up workspace by email
    4. Fire-and-forget background task to fetch and process messages
    5. Return 200 immediately (within 3s for Pub/Sub)
    """
    # Verify token if configured
    if authorization:
        token = authorization.replace("Bearer ", "")
        if not verify_google_pubsub_token(token):
            logger.warning("gmail_webhook_invalid_token")
            raise HTTPException(status_code=401, detail="Invalid token")

    try:
        body = await request.json()
        logger.info("gmail_webhook_received", subscription=body.get("subscription"))

        # Decode the Pub/Sub message
        import base64
        message_data = body.get("message", {}).get("data", "")
        if message_data:
            decoded = json.loads(base64.b64decode(message_data).decode("utf-8"))
            email_address = decoded.get("emailAddress")
            history_id = decoded.get("historyId")

            logger.info(
                "gmail_notification",
                email=email_address,
                history_id=history_id,
            )

            # Look up workspace by email address
            workspace_id = await _get_workspace_by_gmail_email(email_address)
            if workspace_id:
                # Fire-and-forget background processing
                background_tasks.add_task(
                    process_gmail_notification,
                    workspace_id,
                    history_id,
                )
            else:
                logger.warning(
                    "gmail_workspace_not_found",
                    email=email_address,
                )

        return {"status": "ok"}

    except Exception as e:
        logger.exception("gmail_webhook_error", error=str(e))
        # Return 200 to prevent Pub/Sub retries
        return {"status": "error", "message": str(e)}


# =============================================================================
# Slack Webhook - REMOVED
# =============================================================================
# Slack webhook handling has been replaced by Bolt for Python integration.
# See: backend/integrations/slack/bolt_app.py
# Endpoint: POST /slack/events (defined in main.py)


# =============================================================================
# Google Calendar Webhook
# =============================================================================


@router.post("/calendar")
async def calendar_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_goog_channel_id: Optional[str] = Header(None),
    x_goog_resource_state: Optional[str] = Header(None),
):
    """
    Receive Google Calendar push notifications.

    Calendar sends notifications when:
    - Events are created, updated, or deleted
    - The sync token expires
    """
    try:
        channel_id = x_goog_channel_id
        resource_state = x_goog_resource_state

        logger.info(
            "calendar_webhook_received",
            channel_id=channel_id,
            resource_state=resource_state,
        )

        # resource_state can be: sync, exists, not_exists
        if resource_state == "sync":
            # Initial sync notification - just acknowledge
            return {"status": "ok"}

        if resource_state in ("exists", "not_exists"):
            # Calendar event changed
            # Look up workspace by channel_id and fetch updated events
            background_tasks.add_task(
                process_calendar_notification,
                channel_id,
                resource_state,
            )

        return {"status": "ok"}

    except Exception as e:
        logger.exception("calendar_webhook_error", error=str(e))
        return {"status": "error", "message": str(e)}


async def _get_workspace_by_gmail_email(email: str) -> str | None:
    """
    Look up workspace by Gmail email address.

    For now, we use a simple heuristic: find the first active Gmail integration.
    In the future, we could store the email address in the integration config.
    """
    try:
        from db.dataconnect_client import get_dataconnect_client

        dc = get_dataconnect_client()
        result = await dc.execute_query(
            "GetActiveGmailIntegrations",
        )

        integrations = result.get("workspaceIntegrations", [])
        if integrations:
            # For now, just return the first workspace
            # TODO: Store email address in config to match properly
            return integrations[0]["workspace"]["id"]

        return None

    except Exception as e:
        logger.error("get_workspace_by_email_failed", email=email, error=str(e))
        return None


async def process_gmail_notification(workspace_id: str, history_id: str):
    """
    Process Gmail push notification in background.

    Uses fire-and-forget pattern like Slack integration.

    Flow:
    1. Get integration config and history_id watermark
    2. Fetch changes since history_id via GmailClient.get_history()
    3. Fetch full message details for each new message
    4. Convert to ChangeEvents via GmailEventEmitter
    5. Persist to change_events table
    6. Process via SignalWatcherEventProcessor
    """
    try:
        from db.dataconnect_client import get_dataconnect_client
        from services.integration_service_dc import IntegrationServiceDC
        from services.event_emitters.gmail_emitter import GmailEventEmitter
        from integrations.clients.gmail_client import GmailClient

        dc = get_dataconnect_client()
        integration_service = IntegrationServiceDC(dc, workspace_id)

        # Get integration config
        config = await integration_service.get_integration_config("gmail")
        if not config:
            logger.warning("gmail_integration_not_configured", workspace_id=workspace_id)
            return

        # Fetch changes since history_id
        gmail_client = GmailClient(integration_service)
        history = await gmail_client.get_history(
            start_history_id=history_id,
            history_types=["messageAdded"],
        )

        # Convert messages to ChangeEvents
        emitter = GmailEventEmitter(workspace_id, integration_service=integration_service)
        events = []

        for history_item in history.get("history", []):
            for msg_added in history_item.get("messagesAdded", []):
                msg = msg_added.get("message", {})
                msg_id = msg.get("id")

                if not msg_id:
                    continue

                try:
                    # Fetch full message details
                    full_msg = await gmail_client.get_message(msg_id)
                    event = await emitter.convert_gmail_message_to_event(full_msg)

                    if event:
                        events.append(event)

                except Exception as e:
                    logger.warning(
                        "gmail_message_fetch_failed",
                        message_id=msg_id,
                        error=str(e),
                    )
                    continue

        # Persist to change_events table (dedup by fingerprint)
        for event in events:
            try:
                await dc.execute_mutation(
                    "CreateChangeEvent",
                    {
                        # Note: id is auto-generated by the database
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
            except Exception as e:
                # Duplicate fingerprint is expected (idempotent retries)
                if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                    logger.debug("gmail_event_duplicate_skipped", fingerprint=event.fingerprint)
                    continue
                logger.warning(
                    "gmail_event_persist_failed",
                    event_id=str(event.id),
                    error=str(e),
                )
                continue

        # Process via SignalWatcher (if we have events)
        if events:
            try:
                from agents.signal_watcher_unified.event_processor import (
                    SignalWatcherEventProcessor,
                )

                processor = SignalWatcherEventProcessor(workspace_id)
                await processor.process_events(events)

            except Exception as e:
                logger.error(
                    "gmail_signal_processing_failed",
                    workspace_id=workspace_id,
                    error=str(e),
                )
                # Mark all events with processing error
                for event in events:
                    try:
                        await dc.execute_mutation(
                            "MarkChangeEventError",
                            {
                                "eventId": str(event.id),
                                "error": str(e),
                            },
                        )
                    except Exception as mark_error_exc:
                        logger.warning(
                            "failed_to_record_processing_error",
                            event_id=str(event.id),
                            original_error=str(e),
                            mark_error_exception=str(mark_error_exc),
                        )

        logger.info(
            "gmail_notification_processed",
            workspace_id=workspace_id,
            history_id=history_id,
            events_created=len(events),
        )

    except Exception as e:
        logger.error(
            "process_gmail_notification_failed",
            workspace_id=workspace_id,
            error=str(e),
        )


async def process_calendar_notification(channel_id: str, resource_state: str):
    """
    Process Calendar push notification in background.

    Uses fire-and-forget pattern like Gmail/Slack integrations.

    Flow:
    1. Look up workspace by channel_id
    2. Get integration config with sync_token
    3. Fetch calendar events via CalendarClient (incremental sync)
    4. Convert to ChangeEvents via CalendarEventEmitter
    5. Persist to change_events table
    6. Process via SignalWatcherEventProcessor
    """
    try:
        from db.dataconnect_client import get_dataconnect_client
        from services.integration_service_dc import IntegrationServiceDC
        from services.event_emitters.calendar_emitter import CalendarEventEmitter
        from integrations.clients.calendar_client import CalendarClient

        dc = get_dataconnect_client()

        # Look up workspace by channel_id
        result = await dc.execute_query("GetActiveCalendarIntegrations")
        integrations = result.get("workspaceIntegrations", [])

        workspace_id = None
        workspace_domain = None
        for integration in integrations:
            config = integration.get("config", {})
            watch_config = config.get("watch", {})
            if watch_config.get("channel_id") == channel_id:
                workspace = integration.get("workspace", {})
                workspace_id = workspace.get("id")
                workspace_domain = workspace.get("domain")
                break

        if not workspace_id:
            logger.warning("calendar_workspace_not_found", channel_id=channel_id)
            return

        logger.info(
            "calendar_notification_processing",
            workspace_id=workspace_id,
            resource_state=resource_state,
        )

        integration_service = IntegrationServiceDC(dc, workspace_id)

        # Get integration config
        config = await integration_service.get_integration_config("calendar")
        if not config:
            logger.warning("calendar_integration_not_configured", workspace_id=workspace_id)
            return

        # Fetch calendar events using sync token
        calendar_client = CalendarClient(integration_service)
        sync_token = config.get("watch", {}).get("sync_token")

        if sync_token:
            result = await calendar_client.list_events(sync_token=sync_token)
        else:
            # Fallback to time-windowed sync
            from datetime import datetime, timedelta, timezone
            time_min = datetime.now(timezone.utc)
            time_max = time_min + timedelta(days=30)
            result = await calendar_client.list_events(time_min=time_min, time_max=time_max)

        calendar_events = result.get("events", [])
        new_sync_token = result.get("next_sync_token")

        # Update sync token
        if new_sync_token:
            if "watch" not in config:
                config["watch"] = {}
            config["watch"]["sync_token"] = new_sync_token
            await integration_service.update_config("calendar", config, merge=True)

        # Convert to ChangeEvents
        emitter = CalendarEventEmitter(
            workspace_id,
            workspace_domain,
            integration_service=integration_service,
        )
        events = []

        for calendar_event in calendar_events:
            try:
                event = await emitter.convert_calendar_event_to_change_event(calendar_event)
                if event:
                    events.append(event)
            except Exception as e:
                logger.warning(
                    "calendar_event_conversion_failed",
                    event_id=calendar_event.get("id"),
                    error=str(e),
                )
                continue

        # Persist to change_events table (dedup by fingerprint)
        for event in events:
            try:
                await dc.execute_mutation(
                    "CreateChangeEvent",
                    {
                        # Note: id is auto-generated by the database
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
            except Exception as e:
                # Duplicate fingerprint is expected (idempotent retries)
                if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                    logger.debug("calendar_event_duplicate_skipped", fingerprint=event.fingerprint)
                    continue
                logger.warning(
                    "calendar_event_persist_failed",
                    event_id=str(event.id),
                    error=str(e),
                )
                continue

        # Process via SignalWatcher (if we have events)
        if events:
            try:
                from agents.signal_watcher_unified.event_processor import (
                    SignalWatcherEventProcessor,
                )

                processor = SignalWatcherEventProcessor(workspace_id)
                await processor.process_events(events)

            except Exception as e:
                logger.error(
                    "calendar_signal_processing_failed",
                    workspace_id=workspace_id,
                    error=str(e),
                )
                # Mark all events with processing error
                for event in events:
                    try:
                        await dc.execute_mutation(
                            "MarkChangeEventError",
                            {
                                "eventId": str(event.id),
                                "error": str(e),
                            },
                        )
                    except Exception as mark_error_exc:
                        logger.warning(
                            "failed_to_record_processing_error",
                            event_id=str(event.id),
                            original_error=str(e),
                            mark_error_exception=str(mark_error_exc),
                        )

        logger.info(
            "calendar_notification_processed",
            workspace_id=workspace_id,
            channel_id=channel_id,
            events_created=len(events),
        )

    except Exception as e:
        logger.exception("process_calendar_notification_error", error=str(e))


# =============================================================================
# Notion Webhook (via Notion Integration)
# =============================================================================


@router.post("/notion")
async def notion_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Receive Notion database change notifications.

    Used to detect new deals in the CRM database for handoff processing.
    """
    try:
        body = await request.json()
        logger.info("notion_webhook_received")

        # Notion webhooks are still in beta
        # For now, we poll via the autonomous agent
        # This endpoint is a placeholder for when Notion webhooks are available

        return {"status": "ok"}

    except Exception as e:
        logger.exception("notion_webhook_error", error=str(e))
        return {"status": "error", "message": str(e)}


# =============================================================================
# Generic Signal Ingestion Endpoint
# =============================================================================


class IngestSignalRequest(BaseModel):
    """Request to manually ingest a signal."""
    workspace_id: str
    channel: str  # email, slack, calendar, internal
    direction: str = "inbound"  # inbound or outbound
    sender_email: Optional[str] = None
    sender_name: Optional[str] = None
    recipient_email: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    external_id: Optional[str] = None
    metadata: Optional[dict] = None


@router.post("/ingest")
async def ingest_signal(
    request: IngestSignalRequest,
    background_tasks: BackgroundTasks,
):
    """
    Manually ingest a signal for processing.

    This is useful for:
    - Testing the signal processing pipeline
    - Importing historical data
    - Manual signal entry
    """
    logger.info(
        "signal_ingest",
        workspace_id=request.workspace_id,
        channel=request.channel,
        sender=request.sender_email,
    )

    try:
        # Create raw signal
        from db.client import get_db_client
        import uuid
        db = get_db_client()

        signal_id = str(uuid.uuid4())

        await db.execute(
            """
            INSERT INTO raw_signals (
                id, workspace_id, channel, direction,
                sender_email, sender_name, recipient_email,
                subject, body_encrypted, external_id, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            [
                signal_id,
                request.workspace_id,
                request.channel,
                request.direction,
                request.sender_email,
                request.sender_name,
                request.recipient_email,
                request.subject,
                request.body,
                request.external_id,
                json.dumps(request.metadata or {}),
            ],
        )

        # Trigger signal watcher
        background_tasks.add_task(
            run_signal_watcher_auto,
            workspace_id=request.workspace_id,
            trigger_type="manual_ingest",
        )

        return {
            "status": "ok",
            "signal_id": signal_id,
            "message": "Signal queued for processing",
        }

    except Exception as e:
        logger.exception("signal_ingest_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

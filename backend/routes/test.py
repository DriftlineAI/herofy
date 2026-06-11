"""
Test Routes

Endpoints for testing the SignalWatcher pipeline with fake data.
These should only be enabled in development/staging environments.
"""

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
from uuid import UUID, uuid4

from core.logging import get_logger
from core.events import ChangeEvent, ChangeEventSource
from services.event_emitters.gmail_emitter import GmailEventEmitter
from services.event_emitters.slack_emitter import SlackEventEmitter
from agents.signal_watcher_unified.event_processor import SignalWatcherEventProcessor
from db.dataconnect_client import get_dataconnect_client
from services.integration_service_dc import IntegrationServiceDC
from services.health_scoring_service import HealthScoringService

router = APIRouter(tags=["test"])
logger = get_logger("TestRoutes")


def snake_to_camel(snake_str: str) -> str:
    """Convert snake_case to camelCase."""
    components = snake_str.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])


def dict_keys_to_camel(data: dict) -> dict:
    """Convert all dict keys from snake_case to camelCase."""
    return {snake_to_camel(k): v for k, v in data.items()}


# =============================================================================
# Test Payloads
# =============================================================================


class TestGmailMessage(BaseModel):
    """Fake Gmail message for testing"""

    from_email: str = Field(..., description="Sender email address")
    from_name: str = Field("Test User", description="Sender name")
    subject: str = Field("Test Email", description="Email subject")
    body: str = Field("This is a test email.", description="Email body")
    message_id: str = Field("test-message-123", description="Gmail message ID")
    thread_id: str = Field("test-thread-123", description="Gmail thread ID")
    label_ids: list[str] = Field(default_factory=lambda: ["INBOX"], description="Gmail labels")


class TestSlackMessage(BaseModel):
    """Fake Slack message for testing"""

    user_email: str = Field(..., description="Slack user email")
    user_name: str = Field("Test User", description="Slack user name")
    text: str = Field("This is a test Slack message.", description="Message text")
    channel_id: str = Field("C123456", description="Slack channel ID")
    channel_name: str = Field("general", description="Slack channel name")
    timestamp: str = Field("1234567890.123456", description="Slack message timestamp")


class TestCalendarEvent(BaseModel):
    """Fake Calendar event for testing meeting prep needs"""

    customer_id: str = Field(..., description="Customer UUID to link meeting to")
    title: str = Field("Test Meeting", description="Meeting title")
    scheduled_at: datetime = Field(..., description="Meeting start time (ISO format)")
    duration_minutes: int = Field(30, description="Meeting duration in minutes")
    attendees_theirs: list[str] = Field(default_factory=list, description="External attendee emails")
    attendees_ours: list[str] = Field(default_factory=list, description="Internal attendee emails")
    event_id: str = Field("test-calendar-event-123", description="Google Calendar event ID")


class TestProcessResult(BaseModel):
    """Result of test processing"""

    success: bool
    change_event_id: Optional[str] = None
    customer_id: Optional[str] = None
    event_class: Optional[str] = None
    artifacts_created: dict = Field(default_factory=dict)
    processing_error: Optional[str] = None
    steps: list[str] = Field(default_factory=list)


# =============================================================================
# Test Endpoints
# =============================================================================


@router.post("/gmail-message", response_model=TestProcessResult)
async def test_gmail_message(
    workspace_id: str,
    message: TestGmailMessage,
) -> TestProcessResult:
    """
    Test the Gmail → ChangeEvent → SignalWatcher pipeline with a fake email.

    This simulates what happens when a real Gmail push notification arrives:
    1. Converts fake Gmail message to ChangeEvent (using GmailEventEmitter)
    2. Persists ChangeEvent to database
    3. Processes via SignalWatcher (classification, routing, artifact creation)
    4. Returns detailed results for debugging

    Args:
        workspace_id: Target workspace UUID
        message: Fake Gmail message payload

    Returns:
        TestProcessResult with processing details
    """
    logger.info(
        "test_gmail_message",
        workspace_id=workspace_id,
        from_email=message.from_email,
    )

    steps = []

    try:
        # Step 1: Create fake Gmail message payload (pre-parsed format)
        # Note: GmailClient normally parses the Gmail API response into this format
        steps.append("Creating fake Gmail message payload")
        fake_message = {
            "id": message.message_id,
            "thread_id": message.thread_id,
            "label_ids": message.label_ids,
            "from": f"{message.from_name} <{message.from_email}>",
            "subject": message.subject,
            "body": message.body,
            "snippet": message.body[:100],  # First 100 chars
            "internal_date": str(int(datetime.now().timestamp() * 1000)),  # milliseconds since epoch
        }

        # Step 2: Convert to ChangeEvent using GmailEventEmitter
        steps.append("Converting to ChangeEvent via GmailEventEmitter")
        dc = get_dataconnect_client()
        integration_service = IntegrationServiceDC(dc, workspace_id)
        emitter = GmailEventEmitter(workspace_id, integration_service=integration_service)

        change_event = await emitter.convert_gmail_message_to_event(fake_message)

        if not change_event:
            return TestProcessResult(
                success=False,
                processing_error="GmailEventEmitter returned None (likely filtered as system email)",
                steps=steps,
            )

        steps.append(f"ChangeEvent created: {change_event.id}")
        steps.append(f"Customer resolved: {change_event.customer_id or 'None (unknown sender)'}")
        steps.append(f"Fingerprint: {change_event.fingerprint}")

        # Step 3: Persist ChangeEvent to database
        steps.append("Persisting ChangeEvent to database")
        try:
            # CreateChangeEvent only accepts these specific fields (no id - auto-generated)
            db_dict = change_event.to_db_dict()
            mutation_vars = {
                "workspaceId": db_dict["workspace_id"],
                "source": db_dict["source"],
                "sourceEventType": db_dict["source_event_type"],
                "sourceRecordId": db_dict["source_record_id"],
                "fingerprint": db_dict["fingerprint"],
                "customerId": db_dict["customer_id"],
                "rawPayload": db_dict["raw_payload"],
                "occurredAt": db_dict["occurred_at"],
            }
            await dc.execute_mutation("CreateChangeEvent", mutation_vars)
            steps.append("ChangeEvent persisted successfully")
        except Exception as e:
            # Might be duplicate fingerprint - that's okay for testing
            error_msg = str(e)
            if "duplicate" in error_msg.lower():
                steps.append(f"ChangeEvent already exists (duplicate fingerprint) - continuing anyway")
            else:
                raise

        # Step 4: Process via SignalWatcher
        steps.append("Processing via SignalWatcherEventProcessor")
        processor = SignalWatcherEventProcessor(workspace_id)

        # Process the event
        await processor.process_events([change_event])

        steps.append("SignalWatcher processing completed")

        # Step 4.5: Recalculate health score for affected customer
        if change_event.customer_id:
            steps.append(f"Recalculating health score for customer {change_event.customer_id}")
            health_service = HealthScoringService(dc, workspace_id)
            try:
                health_result = await health_service.calculate_health(
                    str(change_event.customer_id),
                    updated_by="system:test_endpoint"
                )
                steps.append(
                    f"Health updated: {health_result.health} "
                    f"(score: {health_result.score}, reason: {health_result.reason})"
                )
            except Exception as e:
                steps.append(f"Health calculation failed: {str(e)}")
                logger.warning("test_health_calculation_failed", error=str(e))

        # Step 5: Fetch the processed event to see results (by fingerprint since ID is auto-generated)
        steps.append("Fetching processed ChangeEvent from database")
        result = await dc.execute_query(
            "GetChangeEventByFingerprint",
            {"workspaceId": workspace_id, "fingerprint": change_event.fingerprint},
        )

        change_events = result.get("changeEvents", [])
        processed_event = change_events[0] if change_events else None
        if not processed_event:
            return TestProcessResult(
                success=False,
                processing_error="Could not fetch processed event from database",
                steps=steps,
            )

        artifacts = processed_event.get("artifactsCreated", {})
        steps.append(f"Artifacts created: {artifacts}")

        return TestProcessResult(
            success=True,
            change_event_id=processed_event.get("id"),
            customer_id=str(change_event.customer_id) if change_event.customer_id else None,
            event_class=processed_event.get("eventClass"),
            artifacts_created=artifacts or {},
            processing_error=processed_event.get("processingError"),
            steps=steps,
        )

    except Exception as e:
        logger.exception("test_gmail_message_failed", error=str(e))
        return TestProcessResult(
            success=False,
            processing_error=str(e),
            steps=steps,
        )


@router.post("/slack-message", response_model=TestProcessResult)
async def test_slack_message(
    workspace_id: str,
    message: TestSlackMessage,
) -> TestProcessResult:
    """
    Test the Slack → ChangeEvent → SignalWatcher pipeline with a fake message.

    This simulates what happens when a real Slack webhook arrives:
    1. Converts fake Slack message to ChangeEvent (using SlackEventEmitter)
    2. Persists ChangeEvent to database
    3. Processes via SignalWatcher (classification, routing, artifact creation)
    4. Returns detailed results for debugging

    Args:
        workspace_id: Target workspace UUID
        message: Fake Slack message payload

    Returns:
        TestProcessResult with processing details
    """
    logger.info(
        "test_slack_message",
        workspace_id=workspace_id,
        user_email=message.user_email,
    )

    steps = []

    try:
        # Step 1: Create fake Slack message payload
        steps.append("Creating fake Slack message payload")
        fake_event = {
            "type": "message",
            "text": message.text,
            "user": "U123456",
            "ts": message.timestamp,
            "channel": message.channel_id,
            "channel_type": "channel",
        }

        # Step 2: Convert to ChangeEvent using SlackEventEmitter
        steps.append("Converting to ChangeEvent via SlackEventEmitter")
        dc = get_dataconnect_client()
        integration_service = IntegrationServiceDC(dc, workspace_id)
        emitter = SlackEventEmitter(workspace_id, integration_service=integration_service)

        # Mock user info (normally fetched from Slack API)
        user_info = {
            "id": "U123456",
            "profile": {
                "email": message.user_email,
                "real_name": message.user_name,
            },
        }

        change_event = await emitter.convert_slack_message_to_event(
            fake_event,
            message.channel_name,
            user_info,
        )

        if not change_event:
            return TestProcessResult(
                success=False,
                processing_error="SlackEventEmitter returned None (likely filtered)",
                steps=steps,
            )

        steps.append(f"ChangeEvent created: {change_event.id}")
        steps.append(f"Customer resolved: {change_event.customer_id or 'None (unknown sender)'}")
        steps.append(f"Fingerprint: {change_event.fingerprint}")

        # Step 3: Persist ChangeEvent to database
        steps.append("Persisting ChangeEvent to database")
        try:
            # CreateChangeEvent only accepts these specific fields (no id - auto-generated)
            db_dict = change_event.to_db_dict()
            mutation_vars = {
                "workspaceId": db_dict["workspace_id"],
                "source": db_dict["source"],
                "sourceEventType": db_dict["source_event_type"],
                "sourceRecordId": db_dict["source_record_id"],
                "fingerprint": db_dict["fingerprint"],
                "customerId": db_dict["customer_id"],
                "rawPayload": db_dict["raw_payload"],
                "occurredAt": db_dict["occurred_at"],
            }
            await dc.execute_mutation("CreateChangeEvent", mutation_vars)
            steps.append("ChangeEvent persisted successfully")
        except Exception as e:
            # Might be duplicate fingerprint - that's okay for testing
            error_msg = str(e)
            if "duplicate" in error_msg.lower():
                steps.append(f"ChangeEvent already exists (duplicate fingerprint) - continuing anyway")
            else:
                raise

        # Step 4: Process via SignalWatcher
        steps.append("Processing via SignalWatcherEventProcessor")
        processor = SignalWatcherEventProcessor(workspace_id)

        # Process the event
        await processor.process_events([change_event])

        steps.append("SignalWatcher processing completed")

        # Step 4.5: Recalculate health score for affected customer
        if change_event.customer_id:
            steps.append(f"Recalculating health score for customer {change_event.customer_id}")
            health_service = HealthScoringService(dc, workspace_id)
            try:
                health_result = await health_service.calculate_health(
                    str(change_event.customer_id),
                    updated_by="system:test_endpoint"
                )
                steps.append(
                    f"Health updated: {health_result.health} "
                    f"(score: {health_result.score}, reason: {health_result.reason})"
                )
            except Exception as e:
                steps.append(f"Health calculation failed: {str(e)}")
                logger.warning("test_health_calculation_failed", error=str(e))

        # Step 5: Fetch the processed event to see results (by fingerprint since ID is auto-generated)
        steps.append("Fetching processed ChangeEvent from database")
        result = await dc.execute_query(
            "GetChangeEventByFingerprint",
            {"workspaceId": workspace_id, "fingerprint": change_event.fingerprint},
        )

        change_events = result.get("changeEvents", [])
        processed_event = change_events[0] if change_events else None
        if not processed_event:
            return TestProcessResult(
                success=False,
                processing_error="Could not fetch processed event from database",
                steps=steps,
            )

        artifacts = processed_event.get("artifactsCreated", {})
        steps.append(f"Artifacts created: {artifacts}")

        return TestProcessResult(
            success=True,
            change_event_id=processed_event.get("id"),
            customer_id=str(change_event.customer_id) if change_event.customer_id else None,
            event_class=processed_event.get("eventClass"),
            artifacts_created=artifacts or {},
            processing_error=processed_event.get("processingError"),
            steps=steps,
        )

    except Exception as e:
        logger.exception("test_slack_message_failed", error=str(e))
        return TestProcessResult(
            success=False,
            processing_error=str(e),
            steps=steps,
        )


@router.post("/calendar-event", response_model=TestProcessResult)
async def test_calendar_event(
    workspace_id: str,
    event: TestCalendarEvent,
) -> TestProcessResult:
    """
    Test the Calendar → ChangeEvent → SignalWatcher pipeline with a fake event.

    This simulates what happens when a real Calendar push notification arrives:
    1. Creates a ChangeEvent for a calendar event
    2. Persists ChangeEvent to database
    3. Processes via SignalWatcher (creates Meeting + meeting_prep_ready Need)
    4. Returns detailed results for debugging

    Args:
        workspace_id: Target workspace UUID
        event: Fake calendar event payload

    Returns:
        TestProcessResult with processing details
    """
    logger.info(
        "test_calendar_event",
        workspace_id=workspace_id,
        customer_id=event.customer_id,
        title=event.title,
        scheduled_at=event.scheduled_at.isoformat(),
    )

    steps = []

    try:
        # Step 1: Create ChangeEvent for calendar
        steps.append("Creating calendar ChangeEvent")

        # Build raw payload matching what CalendarEventEmitter produces
        raw_payload = {
            "title": event.title,
            "scheduled_at": event.scheduled_at.isoformat(),
            "duration_minutes": event.duration_minutes,
            "attendees_theirs": event.attendees_theirs,
            "attendees_ours": event.attendees_ours,
            "calendar_event_id": event.event_id,
            "status": "confirmed",
        }

        change_event = ChangeEvent(
            id=uuid4(),
            workspace_id=UUID(workspace_id),
            source=ChangeEventSource.CALENDAR,
            source_event_type="calendar_event_created",
            source_record_id=event.event_id,
            fingerprint=f"calendar:{workspace_id}:{event.event_id}:{event.scheduled_at.isoformat()}",
            customer_id=UUID(event.customer_id),
            raw_payload=raw_payload,
            occurred_at=datetime.now(timezone.utc),
        )

        steps.append(f"ChangeEvent created: {change_event.id}")
        steps.append(f"Customer ID: {change_event.customer_id}")

        # Step 2: Persist ChangeEvent to database
        steps.append("Persisting ChangeEvent to database")
        dc = get_dataconnect_client()

        try:
            # CreateChangeEvent only accepts these specific fields (no id - auto-generated)
            db_dict = change_event.to_db_dict()
            mutation_vars = {
                "workspaceId": db_dict["workspace_id"],
                "source": db_dict["source"],
                "sourceEventType": db_dict["source_event_type"],
                "sourceRecordId": db_dict["source_record_id"],
                "fingerprint": db_dict["fingerprint"],
                "customerId": db_dict["customer_id"],
                "rawPayload": db_dict["raw_payload"],
                "occurredAt": db_dict["occurred_at"],
            }
            await dc.execute_mutation("CreateChangeEvent", mutation_vars)
            steps.append("ChangeEvent persisted successfully")
        except Exception as e:
            error_msg = str(e)
            if "duplicate" in error_msg.lower():
                steps.append("ChangeEvent already exists (duplicate fingerprint) - continuing anyway")
            else:
                raise

        # Step 3: Process via SignalWatcher
        steps.append("Processing via SignalWatcherEventProcessor")
        processor = SignalWatcherEventProcessor(workspace_id)

        # Process the event
        await processor.process_events([change_event])

        steps.append("SignalWatcher processing completed")

        # Step 4: Fetch the processed event to see results (by fingerprint since ID is auto-generated)
        steps.append("Fetching processed ChangeEvent from database")
        result = await dc.execute_query(
            "GetChangeEventByFingerprint",
            {"workspaceId": workspace_id, "fingerprint": change_event.fingerprint},
        )

        change_events = result.get("changeEvents", [])
        processed_event = change_events[0] if change_events else None
        if not processed_event:
            return TestProcessResult(
                success=False,
                processing_error="Could not fetch processed event from database",
                steps=steps,
            )

        artifacts = processed_event.get("artifactsCreated") or {}
        steps.append(f"Event class: {processed_event.get('eventClass')}")
        steps.append(f"Artifacts created: {json.dumps(artifacts)}")

        # Check if meeting prep need was created
        needs = artifacts.get("needs", []) if artifacts else []
        meetings = artifacts.get("meetings", []) if artifacts else []
        if needs:
            steps.append(f"Meeting prep need created: {needs[0]}")
        if meetings:
            steps.append(f"Meeting created: {meetings[0]}")

        return TestProcessResult(
            success=True,
            change_event_id=processed_event.get("id"),
            customer_id=str(change_event.customer_id),
            event_class=processed_event.get("eventClass"),
            artifacts_created=artifacts or {},
            processing_error=processed_event.get("processingError"),
            steps=steps,
        )

    except Exception as e:
        logger.exception("test_calendar_event_failed", error=str(e))
        return TestProcessResult(
            success=False,
            processing_error=str(e),
            steps=steps,
        )


@router.get("/health")
async def test_health():
    """Health check for test routes"""
    return {"status": "healthy", "service": "test-routes"}

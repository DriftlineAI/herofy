"""
Internal API Routes

Endpoints for scheduled background jobs, monitoring, and system tasks.
Should be secured with internal API key authentication.
"""

from fastapi import APIRouter, Header, HTTPException
from typing import Annotated

from core.logging import get_logger
from config import get_settings

router = APIRouter(prefix="/internal", tags=["internal"])
logger = get_logger("InternalRoutes")


def verify_internal_key(authorization: str | None = Header(None)) -> None:
    """
    Verify internal API key from Authorization header.

    Raises:
        HTTPException: If key is missing or invalid
    """
    settings = get_settings()
    expected_key = settings.internal_api_key

    if not expected_key:
        # If no key configured, allow all (dev mode)
        logger.warning("internal_api_key_not_configured")
        return

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    # Format: "Bearer <key>"
    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    provided_key = parts[1]
    if provided_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


# =============================================================================
# Watch Channel Renewal
# =============================================================================


@router.post("/renew-watches")
async def renew_all_watches(
    authorization: Annotated[str | None, Header()] = None,
):
    """
    Renew Gmail and Calendar watch channels for all workspaces.

    Should be triggered weekly by Cloud Scheduler.

    Security:
        Requires internal API key in Authorization header.

    Returns:
        Statistics about renewed watch channels
    """
    verify_internal_key(authorization)

    logger.info("renew_watches_triggered")

    try:
        from services.gmail_watch_renewal import (
            renew_gmail_watches,
            renew_calendar_watches,
        )

        # Renew both Gmail and Calendar watches
        gmail_stats = await renew_gmail_watches()
        calendar_stats = await renew_calendar_watches()

        logger.info(
            "renew_watches_completed",
            gmail_stats=gmail_stats,
            calendar_stats=calendar_stats,
        )

        return {
            "status": "success",
            "gmail": gmail_stats,
            "calendar": calendar_stats,
        }

    except Exception as e:
        logger.exception("renew_watches_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Watch renewal failed: {str(e)}")


# =============================================================================
# Polling Fallback
# =============================================================================


@router.post("/poll-integrations")
async def poll_all_integrations(
    authorization: Annotated[str | None, Header()] = None,
):
    """
    Poll all integrations for new data (fallback for push notifications).

    Should be triggered every 15 minutes by Cloud Scheduler.

    Security:
        Requires internal API key in Authorization header.

    Returns:
        Statistics about polling results
    """
    verify_internal_key(authorization)

    logger.info("poll_integrations_triggered")

    try:
        from db.dataconnect_client import get_dataconnect_client

        dc = get_dataconnect_client()

        # Get all active Gmail integrations
        gmail_result = await dc.execute_query("GetActiveGmailIntegrations")
        gmail_integrations = gmail_result.get("workspaceIntegrations", [])

        stats = {
            "gmail": {
                "workspaces_checked": len(gmail_integrations),
                "events_created": 0,
                "errors": 0,
            }
        }

        # Poll each Gmail integration
        for integration in gmail_integrations:
            workspace = integration.get("workspace", {})
            workspace_id = workspace.get("id")

            if not workspace_id:
                continue

            try:
                from services.event_emitters.gmail_emitter import GmailEventEmitter
                from services.integration_service_dc import IntegrationServiceDC
                from agents.signal_watcher_unified.event_processor import (
                    SignalWatcherEventProcessor,
                )

                integration_service = IntegrationServiceDC(dc, workspace_id)
                emitter = GmailEventEmitter(workspace_id, integration_service=integration_service)

                # Poll for new events
                events = await emitter.poll_and_emit()

                # Persist to change_events table
                for event in events:
                    try:
                        # CreateChangeEvent only accepts these specific fields (no id - auto-generated)
                        db_dict = event.to_db_dict()
                        await dc.execute_mutation(
                            "CreateChangeEvent",
                            {
                                "workspaceId": db_dict["workspace_id"],
                                "source": db_dict["source"],
                                "sourceEventType": db_dict["source_event_type"],
                                "sourceRecordId": db_dict["source_record_id"],
                                "fingerprint": db_dict["fingerprint"],
                                "customerId": db_dict["customer_id"],
                                "rawPayload": db_dict["raw_payload"],
                                "occurredAt": db_dict["occurred_at"],
                            },
                        )
                    except Exception as e:
                        logger.warning(
                            "poll_event_persist_failed",
                            workspace_id=workspace_id,
                            event_id=str(event.id),
                            error=str(e),
                        )

                # Process via SignalWatcher
                if events:
                    processor = SignalWatcherEventProcessor(workspace_id)
                    await processor.process_events(events)

                stats["gmail"]["events_created"] += len(events)

                logger.info(
                    "gmail_polling_completed",
                    workspace_id=workspace_id,
                    events_created=len(events),
                )

            except Exception as e:
                stats["gmail"]["errors"] += 1
                logger.error(
                    "gmail_polling_failed",
                    workspace_id=workspace_id,
                    error=str(e),
                )

        logger.info("poll_integrations_completed", stats=stats)

        return {
            "status": "success",
            "stats": stats,
        }

    except Exception as e:
        logger.exception("poll_integrations_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Polling failed: {str(e)}")


# =============================================================================
# Health Check
# =============================================================================


@router.get("/health")
async def internal_health_check():
    """
    Health check endpoint for internal monitoring.

    No authentication required.
    """
    return {"status": "healthy", "service": "herofy-backend"}

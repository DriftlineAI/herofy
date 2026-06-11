"""
Gmail Watch Channel Renewal Service

Renews Gmail watch channels before they expire (7-day expiration).
Should be triggered weekly by Cloud Scheduler.
"""

from datetime import datetime, timedelta, timezone
import json

from core.logging import get_logger

logger = get_logger("GmailWatchRenewal")


async def renew_gmail_watches() -> dict[str, int]:
    """
    Renew Gmail watch channels for all active Gmail integrations.

    Checks all active Gmail integrations and renews watch channels
    that are expiring within 24 hours.

    Returns:
        Dict with renewal statistics:
        {
            "checked": int,
            "renewed": int,
            "failed": int,
        }
    """
    from db.dataconnect_client import get_dataconnect_client
    from services.integration_service_dc import IntegrationServiceDC
    from integrations.clients.gmail_client import GmailClient
    from config import get_settings

    stats = {
        "checked": 0,
        "renewed": 0,
        "failed": 0,
    }

    try:
        dc = get_dataconnect_client()
        settings = get_settings()

        # Get all active Gmail integrations
        result = await dc.execute_query("GetActiveGmailIntegrations")
        integrations = result.get("workspaceIntegrations", [])

        logger.info(
            "gmail_watch_renewal_started",
            integration_count=len(integrations),
        )

        for integration in integrations:
            stats["checked"] += 1

            workspace = integration.get("workspace", {})
            workspace_id = workspace.get("id")

            if not workspace_id:
                logger.warning("gmail_integration_no_workspace_id")
                continue

            # Parse config
            config = integration.get("config", {})
            if isinstance(config, str):
                config = json.loads(config)

            watch_config = config.get("watch", {})
            expiration = watch_config.get("expiration")

            if not expiration:
                logger.info(
                    "gmail_watch_no_expiration",
                    workspace_id=workspace_id,
                )
                continue

            # Check if expiring within 24 hours
            expires_at = datetime.fromtimestamp(expiration / 1000, tz=timezone.utc)
            now = datetime.now(timezone.utc)
            hours_until_expiry = (expires_at - now).total_seconds() / 3600

            logger.debug(
                "gmail_watch_checked",
                workspace_id=workspace_id,
                hours_until_expiry=round(hours_until_expiry, 1),
            )

            # Renew if expiring within 24 hours
            if expires_at < now + timedelta(hours=24):
                try:
                    integration_service = IntegrationServiceDC(dc, workspace_id)
                    gmail_client = GmailClient(integration_service)

                    # Get Pub/Sub topic from config
                    pubsub_topic = settings.google_pubsub_topic
                    if not pubsub_topic:
                        logger.error(
                            "gmail_watch_renewal_no_topic",
                            workspace_id=workspace_id,
                        )
                        stats["failed"] += 1
                        continue

                    # Create new watch channel
                    watch_response = await gmail_client.setup_watch(
                        topic_name=pubsub_topic,
                        label_ids=["INBOX"],
                    )

                    # Update watch config
                    new_config = {
                        "watch": {
                            "history_id": watch_response["historyId"],
                            "expiration": watch_response["expiration"],
                        },
                    }

                    await integration_service.update_config("gmail", new_config, merge=True)

                    stats["renewed"] += 1

                    logger.info(
                        "gmail_watch_renewed",
                        workspace_id=workspace_id,
                        old_expiration=expiration,
                        new_expiration=watch_response["expiration"],
                    )

                except Exception as e:
                    stats["failed"] += 1
                    logger.error(
                        "gmail_watch_renewal_failed",
                        workspace_id=workspace_id,
                        error=str(e),
                    )

        logger.info(
            "gmail_watch_renewal_completed",
            **stats,
        )

        return stats

    except Exception as e:
        logger.exception("gmail_watch_renewal_error", error=str(e))
        raise


async def renew_calendar_watches() -> dict[str, int]:
    """
    Renew Calendar watch channels for all active Calendar integrations.

    Similar to Gmail watch renewal but for Calendar (also expires after 7 days).

    Returns:
        Dict with renewal statistics
    """
    from db.dataconnect_client import get_dataconnect_client
    from services.integration_service_dc import IntegrationServiceDC
    from integrations.clients.calendar_client import CalendarClient
    from config import get_settings
    from uuid import uuid4

    stats = {
        "checked": 0,
        "renewed": 0,
        "failed": 0,
    }

    try:
        dc = get_dataconnect_client()
        settings = get_settings()

        # Get all active Calendar integrations
        result = await dc.execute_query("GetActiveCalendarIntegrations")
        integrations = result.get("workspaceIntegrations", [])

        logger.info(
            "calendar_watch_renewal_started",
            integration_count=len(integrations),
        )

        for integration in integrations:
            stats["checked"] += 1

            workspace = integration.get("workspace", {})
            workspace_id = workspace.get("id")

            if not workspace_id:
                logger.warning("calendar_integration_no_workspace_id")
                continue

            # Parse config
            config = integration.get("config", {})
            if isinstance(config, str):
                config = json.loads(config)

            watch_config = config.get("watch", {})
            expiration = watch_config.get("expiration")

            if not expiration:
                logger.info(
                    "calendar_watch_no_expiration",
                    workspace_id=workspace_id,
                )
                continue

            # Check if expiring within 24 hours
            expires_at = datetime.fromtimestamp(expiration / 1000, tz=timezone.utc)
            now = datetime.now(timezone.utc)
            hours_until_expiry = (expires_at - now).total_seconds() / 3600

            logger.debug(
                "calendar_watch_checked",
                workspace_id=workspace_id,
                hours_until_expiry=round(hours_until_expiry, 1),
            )

            # Renew if expiring within 24 hours
            if expires_at < now + timedelta(hours=24):
                try:
                    integration_service = IntegrationServiceDC(dc, workspace_id)
                    calendar_client = CalendarClient(integration_service)

                    # Generate new channel ID
                    channel_id = str(uuid4())

                    # Get webhook URL
                    webhook_url = f"{settings.api_base_url}/webhooks/calendar"

                    # Stop old watch channel (if we have resource_id)
                    old_channel_id = watch_config.get("channel_id")
                    old_resource_id = watch_config.get("resource_id")
                    if old_channel_id and old_resource_id:
                        try:
                            await calendar_client.stop_watch(
                                channel_id=old_channel_id,
                                resource_id=old_resource_id,
                            )
                        except Exception as e:
                            logger.warning(
                                "calendar_watch_stop_failed",
                                workspace_id=workspace_id,
                                error=str(e),
                            )

                    # Create new watch channel
                    watch_response = await calendar_client.setup_watch(
                        channel_id=channel_id,
                        address=webhook_url,
                    )

                    # Update watch config
                    new_config = {
                        "watch": {
                            "channel_id": channel_id,
                            "resource_id": watch_response["resourceId"],
                            "expiration": watch_response["expiration"],
                            "sync_token": watch_config.get("sync_token"),  # Preserve sync token
                        },
                    }

                    await integration_service.update_config("calendar", new_config, merge=True)

                    stats["renewed"] += 1

                    logger.info(
                        "calendar_watch_renewed",
                        workspace_id=workspace_id,
                        old_expiration=expiration,
                        new_expiration=watch_response["expiration"],
                        new_channel_id=channel_id,
                    )

                except Exception as e:
                    stats["failed"] += 1
                    logger.error(
                        "calendar_watch_renewal_failed",
                        workspace_id=workspace_id,
                        error=str(e),
                    )

        logger.info(
            "calendar_watch_renewal_completed",
            **stats,
        )

        return stats

    except Exception as e:
        logger.exception("calendar_watch_renewal_error", error=str(e))
        raise

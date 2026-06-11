"""
Google Calendar API Client
Uses google-api-python-client for Calendar API access.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from core.logging import get_logger
from core.errors import IntegrationAuthError
from services.integration_service_dc import IntegrationServiceDC
from core.types import IntegrationType

logger = get_logger("CalendarClient")


class CalendarClient:
    """
    Google Calendar API client using google-api-python-client.

    Note: The google-api-python-client is synchronous, so methods use
    run_in_executor to avoid blocking the event loop.

    Docs: https://developers.google.com/calendar/api/v3/reference
    """

    def __init__(self, integration_service: IntegrationServiceDC):
        """
        Initialize Calendar client.

        Args:
            integration_service: Service for getting valid tokens
        """
        self.integration_service = integration_service
        self._service = None

    async def _get_service(self):
        """Build Calendar API service with valid credentials."""
        # Calendar uses the same token as Gmail (bundled OAuth)
        access_token = await self.integration_service.get_valid_token(
            IntegrationType.GMAIL  # Calendar scopes included in Gmail OAuth
        )

        # Create credentials object
        credentials = Credentials(token=access_token)

        # Build Calendar API service (runs in executor since it's sync)
        loop = asyncio.get_event_loop()
        service = await loop.run_in_executor(
            None,
            lambda: build("calendar", "v3", credentials=credentials),
        )

        return service

    async def list_events(
        self,
        calendar_id: str = "primary",
        time_min: datetime | None = None,
        time_max: datetime | None = None,
        sync_token: str | None = None,
        max_results: int = 250,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """
        List calendar events.

        Args:
            calendar_id: Calendar ID (default 'primary')
            time_min: Start of time range (ISO format)
            time_max: End of time range (ISO format)
            sync_token: Token for incremental sync
            max_results: Max events to return (up to 2500)
            page_token: Token for pagination

        Returns:
            {
                "events": [...],
                "next_page_token": "...",
                "next_sync_token": "..."
            }
        """
        try:
            service = await self._get_service()

            params = {
                "calendarId": calendar_id,
                "maxResults": min(max_results, 2500),
                "singleEvents": True,  # Expand recurring events
                "orderBy": "startTime",
            }

            if sync_token:
                # Incremental sync
                params["syncToken"] = sync_token
            else:
                # Time-windowed sync
                if time_min:
                    params["timeMin"] = time_min.isoformat()
                if time_max:
                    params["timeMax"] = time_max.isoformat()

            if page_token:
                params["pageToken"] = page_token

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: service.events().list(**params).execute(),
            )

            logger.info(
                "calendar_events_listed",
                count=len(result.get("items", [])),
                has_sync_token=bool(result.get("nextSyncToken")),
            )

            return {
                "events": result.get("items", []),
                "next_page_token": result.get("nextPageToken"),
                "next_sync_token": result.get("nextSyncToken"),
            }

        except HttpError as e:
            if e.resp.status == 401:
                raise IntegrationAuthError(
                    f"Calendar auth failed: {e}",
                    provider="calendar",
                )
            logger.error("calendar_list_events_failed", error=str(e))
            raise

    async def get_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        """
        Get a single calendar event.

        Args:
            event_id: Event ID
            calendar_id: Calendar ID (default 'primary')

        Returns:
            Event object
        """
        try:
            service = await self._get_service()

            loop = asyncio.get_event_loop()
            event = await loop.run_in_executor(
                None,
                lambda: service.events()
                .get(calendarId=calendar_id, eventId=event_id)
                .execute(),
            )

            return event

        except HttpError as e:
            if e.resp.status == 401:
                raise IntegrationAuthError(
                    f"Calendar auth failed: {e}",
                    provider="calendar",
                )
            logger.error(
                "calendar_get_event_failed",
                event_id=event_id,
                error=str(e),
            )
            raise

    async def setup_watch(
        self,
        channel_id: str,
        address: str,
        calendar_id: str = "primary",
        expiration: int | None = None,
    ) -> dict[str, Any]:
        """
        Setup Calendar push notifications.

        Args:
            channel_id: Unique channel ID (UUID)
            address: Webhook URL
            calendar_id: Calendar to watch (default 'primary')
            expiration: Unix timestamp in milliseconds (max 7 days from now)

        Returns:
            {
                "id": channel_id,
                "resourceId": "google-generated-id",
                "expiration": timestamp_ms
            }
        """
        try:
            service = await self._get_service()

            if expiration is None:
                # Default to 7 days (max allowed by Google)
                exp_time = datetime.now(timezone.utc) + timedelta(days=7)
                expiration = int(exp_time.timestamp() * 1000)

            body = {
                "id": channel_id,
                "type": "web_hook",
                "address": address,
                "expiration": expiration,
            }

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: service.events()
                .watch(calendarId=calendar_id, body=body)
                .execute(),
            )

            logger.info(
                "calendar_watch_enabled",
                channel_id=channel_id,
                resource_id=response.get("resourceId"),
                expiration=response.get("expiration"),
            )

            return response

        except HttpError as e:
            if e.resp.status == 401:
                raise IntegrationAuthError(
                    f"Calendar auth failed: {e}",
                    provider="calendar",
                )
            logger.error("calendar_watch_failed", error=str(e))
            raise

    async def stop_watch(
        self,
        channel_id: str,
        resource_id: str,
    ) -> None:
        """
        Stop Calendar push notifications.

        Args:
            channel_id: Channel ID from setup_watch
            resource_id: Resource ID from setup_watch response
        """
        try:
            service = await self._get_service()

            body = {
                "id": channel_id,
                "resourceId": resource_id,
            }

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: service.channels().stop(body=body).execute(),
            )

            logger.info("calendar_watch_stopped", channel_id=channel_id)

        except HttpError as e:
            if e.resp.status == 401:
                raise IntegrationAuthError(
                    f"Calendar auth failed: {e}",
                    provider="calendar",
                )
            logger.error("calendar_stop_watch_failed", error=str(e))
            raise

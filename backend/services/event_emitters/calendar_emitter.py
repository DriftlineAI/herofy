"""
Calendar Event Emitter

Polls Google Calendar for events and emits ChangeEvents.
Follows the EventEmitterBase pattern.
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
)
from services.integration_service_dc import IntegrationServiceDC
from integrations.clients.calendar_client import CalendarClient
from services.event_filters.calendar_filters import CalendarEventFilter
from services.calendar_attendee_resolver import CalendarAttendeeResolver

from .base import EventEmitterBase

logger = get_logger("CalendarEmitter")


class CalendarEventEmitter(EventEmitterBase):
    """
    Calendar event emitter - converts calendar events to ChangeEvents.

    Handles:
    - Event filtering (all-day, single-person, etc.)
    - Attendee resolution (internal vs external)
    - Customer linking (primary customer determination)
    - Recurring event instance tracking
    - Meeting lifecycle (created, modified, canceled)
    """

    def __init__(
        self,
        workspace_id: str,
        workspace_domain: str,
        db: Any = None,  # Kept for backward compatibility but unused
        integration_service: IntegrationServiceDC | None = None,
    ):
        super().__init__(workspace_id, db)
        self.workspace_domain = workspace_domain

        if integration_service is None:
            from db.dataconnect_client import get_dataconnect_client
            dc = get_dataconnect_client()
            integration_service = IntegrationServiceDC(dc, workspace_id)
        self.integration_service = integration_service
        self._calendar_client: CalendarClient | None = None

    @property
    def calendar_client(self) -> CalendarClient:
        """Get or create Calendar client (lazy initialization)."""
        if self._calendar_client is None:
            self._calendar_client = CalendarClient(self.integration_service)
        return self._calendar_client

    def _get_source_type(self) -> ChangeEventSource:
        return ChangeEventSource.CALENDAR

    async def poll_and_emit(
        self,
        since: datetime | None = None,
    ) -> list[ChangeEvent]:
        """
        Fetch calendar events and emit ChangeEvents.

        Uses incremental sync via syncToken for efficiency.
        Falls back to time-windowed sync if no syncToken.

        Args:
            since: Not used for calendar (uses sync tokens instead)

        Returns:
            List of ChangeEvent objects
        """
        try:
            config = await self.get_integration_config()
            if not config:
                raise IntegrationNotConfiguredError("Calendar integration not configured")

            # Get stored sync token
            sync_token = config.get("watch", {}).get("sync_token")

            if sync_token:
                # Incremental sync
                result = await self.calendar_client.list_events(
                    sync_token=sync_token,
                )
            else:
                # Initial sync - next 30 days
                time_min = datetime.now(timezone.utc)
                time_max = time_min + timedelta(days=30)
                result = await self.calendar_client.list_events(
                    time_min=time_min,
                    time_max=time_max,
                )

            events = result["events"]
            new_sync_token = result.get("next_sync_token")

            # Update sync token
            if new_sync_token:
                if "watch" not in config:
                    config["watch"] = {}
                config["watch"]["sync_token"] = new_sync_token
                await self.integration_service.update_config("calendar", config, merge=True)

            # Convert to ChangeEvents
            change_events = []
            for event in events:
                change_event = await self.convert_calendar_event_to_change_event(event)
                if change_event:
                    change_events.append(change_event)

            logger.info(
                "calendar_events_emitted",
                workspace_id=self.workspace_id,
                count=len(change_events),
                total_events=len(events),
            )

            return change_events

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

    async def convert_calendar_event_to_change_event(
        self,
        event: dict[str, Any],
    ) -> ChangeEvent | None:
        """
        Convert Calendar event to ChangeEvent.

        PUBLIC METHOD - Called from:
        - Webhook handler (push notifications)
        - poll_and_emit() (periodic sync)

        Includes:
        - Event filtering (all-day, declined, etc.)
        - Attendee resolution (internal/external split)
        - Customer linking determination
        - Lifecycle status determination (confirmed/canceled)

        Args:
            event: Google Calendar event object

        Returns:
            ChangeEvent or None if filtered out
        """
        # Get filter config
        config = await self.get_integration_config()
        filter_config = config.get("filters", {}) if config else {}
        event_filter = CalendarEventFilter(filter_config)

        # Apply filters
        should_import, skip_reason = event_filter.should_import_event(
            event, self.workspace_domain
        )
        if not should_import:
            logger.debug(
                "calendar_event_skipped",
                event_id=event.get("id"),
                reason=skip_reason,
            )
            return None

        # Resolve attendees
        resolver = CalendarAttendeeResolver(self.workspace_id, self.workspace_domain)
        attendee_data = await resolver.resolve_event_attendees(event)

        # Skip unlinked meetings (per user requirement)
        if attendee_data["link_status"] == "unlinked":
            logger.debug(
                "calendar_event_unlinked",
                event_id=event.get("id"),
                title=event.get("summary"),
            )
            # Still create ChangeEvent but mark unlinked
            # Will be filtered out in SignalWatcher

        # Parse event data
        event_id = event.get("id")
        status = event.get("status", "confirmed")  # "confirmed" | "tentative" | "cancelled"
        recurring_event_id = event.get("recurringEventId")

        start_time = self._parse_datetime(event.get("start", {}))
        end_time = self._parse_datetime(event.get("end", {}))
        duration_minutes = (
            int((end_time - start_time).total_seconds() / 60)
            if start_time and end_time
            else None
        )

        # Determine source_event_type based on status
        if status == "cancelled":
            source_event_type = "calendar_event_canceled"
        elif event.get("updated"):
            # If event has been updated, it might be a modification
            # For hackathon, we'll treat all non-canceled events as "created"
            # A more robust implementation would track previous state
            source_event_type = "calendar_event_created"
        else:
            source_event_type = "calendar_event_created"

        # Compute fingerprint
        fingerprint = ChangeEvent.compute_fingerprint(
            "calendar",
            event_id,
            "",
        )

        # Build raw payload
        raw_payload = {
            "calendar_event_id": event_id,
            "recurring_event_id": recurring_event_id,
            "title": event.get("summary", "Untitled Meeting"),
            "description": event.get("description", ""),
            "location": event.get("location", ""),
            "status": status,
            "scheduled_at": start_time.isoformat() if start_time else None,
            "duration_minutes": duration_minutes,
            "attendees_ours": attendee_data["attendees_ours"],
            "attendees_theirs": attendee_data["attendees_theirs"],
            "link_status": attendee_data["link_status"],
            "hangout_link": event.get("hangoutLink"),
            "conference_data": event.get("conferenceData", {}),
        }

        return ChangeEvent(
            id=uuid4(),
            workspace_id=UUID(self.workspace_id),
            source=ChangeEventSource.CALENDAR,
            source_event_type=source_event_type,
            source_record_id=event_id,
            fingerprint=fingerprint,
            customer_id=attendee_data["customer_id"],
            raw_payload=raw_payload,
            occurred_at=start_time or datetime.now(timezone.utc),
        )

    def _parse_datetime(self, dt_obj: dict) -> datetime | None:
        """Parse Google Calendar datetime object."""
        if "dateTime" in dt_obj:
            dt_str = dt_obj["dateTime"]
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        elif "date" in dt_obj:
            # All-day event - use start of day
            date_str = dt_obj["date"]
            return datetime.fromisoformat(f"{date_str}T00:00:00+00:00")
        return None

"""
Calendar Event Filters

Applies user-configurable filters to calendar events before ingestion.
Default filters skip all-day events, single-person events, declined events, etc.
"""

from datetime import datetime
from typing import Any

from core.logging import get_logger

logger = get_logger("CalendarEventFilter")


# Default filter configuration (used if not specified in integration config)
DEFAULT_FILTER_CONFIG = {
    "skip_all_day": True,
    "skip_single_person": True,
    "skip_declined": True,
    "require_external_attendee": True,
    "min_duration_minutes": 15,
    "event_types_to_skip": ["focusTime", "outOfOffice"],
}


class CalendarEventFilter:
    """
    Apply user-configured filters to calendar events.

    Filters stored in WorkspaceIntegration.config["filters"].
    """

    def __init__(self, filter_config: dict | None = None):
        """
        Initialize filter with configuration.

        Args:
            filter_config: Filter settings dict. Uses defaults if None.
        """
        self.config = {**DEFAULT_FILTER_CONFIG, **(filter_config or {})}

    def should_import_event(
        self, event: dict, workspace_domain: str
    ) -> tuple[bool, str | None]:
        """
        Check if event should be imported.

        Args:
            event: Google Calendar event object
            workspace_domain: Workspace email domain

        Returns:
            (should_import, skip_reason)
        """
        # Skip all-day events
        if self.config.get("skip_all_day", True):
            start = event.get("start", {})
            if "date" in start:  # All-day events use "date" not "dateTime"
                return False, "all_day_event"

        # Skip declined events
        if self.config.get("skip_declined", True):
            attendees = event.get("attendees", [])
            for att in attendees:
                if att.get("self") and att.get("responseStatus") == "declined":
                    return False, "declined_by_user"

        # Skip single-person events
        if self.config.get("skip_single_person", True):
            attendees = event.get("attendees", [])
            if len(attendees) <= 1:
                return False, "single_person"

        # Skip focus time / OOO
        event_type = event.get("eventType")
        skip_types = self.config.get("event_types_to_skip", [])
        if event_type in skip_types:
            return False, f"event_type_{event_type}"

        # Skip very short events
        min_duration = self.config.get("min_duration_minutes", 15)
        start_time = self._parse_datetime(event.get("start", {}))
        end_time = self._parse_datetime(event.get("end", {}))
        if start_time and end_time:
            duration = (end_time - start_time).total_seconds() / 60
            if duration < min_duration:
                return False, "too_short"

        # Require external attendee
        if self.config.get("require_external_attendee", True):
            has_external = self._has_external_attendee(event, workspace_domain)
            if not has_external:
                return False, "no_external_attendees"

        return True, None

    def _has_external_attendee(self, event: dict, workspace_domain: str) -> bool:
        """Check if event has at least one external attendee."""
        attendees = event.get("attendees", [])
        for att in attendees:
            email = att.get("email", "")
            domain = email.split("@")[-1].lower() if "@" in email else ""
            if domain != workspace_domain.lower():
                return True
        return False

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

"""
Signal Source Base
Abstract interface for signal sources (Gmail, Slack, Notion)
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from db.dataconnect_client import get_dataconnect_client
from core.logging import get_logger
from ..models import RawSignal, SignalSource

logger = get_logger("SignalSource")


class SignalSourceBase(ABC):
    """
    Abstract base class for signal sources.

    Implementations must provide:
    - fetch_signals(): Get new signals since watermark
    - _get_source_type(): Return the SignalSource enum value

    Watermark management is handled by the base class using DataConnect.
    """

    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id
        self.dc = get_dataconnect_client()
        self._watermark_key = f"signal_watcher:{self._get_source_type().value}:watermark"

    @abstractmethod
    def _get_source_type(self) -> SignalSource:
        """Return the signal source type (gmail, slack, notion)."""
        pass

    @abstractmethod
    async def fetch_signals(self, since: datetime | None = None) -> list[RawSignal]:
        """
        Fetch new signals since the given timestamp.

        Args:
            since: Only fetch signals after this time. If None, uses stored watermark.

        Returns:
            List of raw signals from this source
        """
        pass

    async def get_watermark(self) -> datetime | None:
        """
        Get the last processed watermark for this source.

        Returns:
            Last processed timestamp, or None if never processed
        """
        result = await self.dc.execute_query(
            "GetAgentState",
            {
                "workspaceId": self.workspace_id,
                "key": self._watermark_key,
            },
        )

        state = result.get("agentState")
        if state and state.get("value"):
            try:
                return datetime.fromisoformat(state["value"])
            except (ValueError, TypeError):
                logger.warning(
                    "invalid_watermark",
                    key=self._watermark_key,
                    value=state["value"],
                )
                return None
        return None

    async def update_watermark(self, timestamp: datetime) -> None:
        """
        Update the watermark after successful processing.

        Args:
            timestamp: New watermark timestamp
        """
        await self.dc.execute_mutation(
            "UpsertAgentState",
            {
                "workspaceId": self.workspace_id,
                "key": self._watermark_key,
                "value": timestamp.isoformat(),
            },
        )

        logger.info(
            "watermark_updated",
            source=self._get_source_type().value,
            timestamp=timestamp.isoformat(),
        )

    async def fetch_new_signals(self) -> list[RawSignal]:
        """
        Convenience method: fetch signals since last watermark.

        Returns:
            List of new signals
        """
        watermark = await self.get_watermark()
        signals = await self.fetch_signals(since=watermark)

        logger.info(
            "signals_fetched",
            source=self._get_source_type().value,
            count=len(signals),
            since=watermark.isoformat() if watermark else "beginning",
        )

        return signals

    def _parse_email_domain(self, email: str | None) -> str | None:
        """Extract domain from email address."""
        if not email or "@" not in email:
            return None
        return email.split("@")[1].lower()

"""
Engagement Trend Service

Analyzes engagement trends from interaction history to provide insight into
customer activity patterns. Computes trends on-demand from existing
interaction data.

Engagement is measured by:
- Interaction frequency (emails, slack messages, meetings)
- Direction balance (customer-initiated vs us-initiated)
- Channel diversity (multi-channel engagement is healthier)

Used by:
- RightRail to show engagement trends
- Today Queue to surface engagement shifts
- Customer Detail to show activity patterns
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal
from enum import Enum
from collections import defaultdict

from db.dataconnect_client import DataConnectClient, get_dataconnect_client
from core.logging import get_logger

logger = get_logger("EngagementTrendService")


class EngagementDirection(str, Enum):
    """Direction of engagement trend over time."""
    INCREASING = "increasing"
    STABLE = "stable"
    DECREASING = "decreasing"
    GOING_DARK = "going_dark"  # No recent activity


@dataclass
class DailyEngagement:
    """Engagement data for a single day."""
    date: str  # ISO date string (YYYY-MM-DD)
    total: int
    inbound: int  # Customer-initiated
    outbound: int  # Us-initiated
    channels: list[str]


@dataclass
class EngagementTrend:
    """Result of engagement trend analysis."""
    direction: EngagementDirection
    confidence: float  # 0.0-1.0 based on data quality
    summary: str  # Human-readable summary

    # Counts
    total_interactions: int
    inbound_count: int  # Customer-initiated
    outbound_count: int  # Us-initiated

    # Time-series data (for sparklines)
    daily_data: list[DailyEngagement]

    # Derived metrics
    days_since_last_interaction: int | None
    average_weekly_interactions: float
    channel_breakdown: dict[str, int]

    window_days: int


@dataclass
class EngagementComparison:
    """Comparison of engagement between two time periods."""
    current_count: int
    previous_count: int
    delta: int
    percent_change: float | None
    interpretation: str


class EngagementTrendService:
    """
    Analyzes engagement trends from interaction history.

    Computes trends on-demand from existing Interaction records.
    No persistent storage required - all computed at query time.
    """

    def __init__(self, dc: DataConnectClient | None = None, workspace_id: str | None = None):
        """
        Initialize service.

        Args:
            dc: DataConnect client (optional, will get singleton if not provided)
            workspace_id: Workspace UUID string
        """
        self.dc = dc or get_dataconnect_client()
        self.workspace_id = workspace_id

    async def get_engagement_trend(
        self,
        customer_id: str,
        window_days: int = 30
    ) -> EngagementTrend:
        """
        Compute engagement trend for a customer over time window.

        Algorithm:
        1. Fetch interactions from last N days
        2. Group by day
        3. Analyze trajectory (increasing/stable/decreasing/going_dark)
        4. Return structured trend with daily data for sparklines

        Args:
            customer_id: Customer UUID string
            window_days: Number of days to analyze

        Returns:
            EngagementTrend with direction, confidence, and daily data
        """
        since = datetime.now(timezone.utc) - timedelta(days=window_days)

        # Fetch interactions
        result = await self.dc.execute_query(
            "GetInteractionsForEngagementTrend",
            {
                "workspaceId": self.workspace_id,
                "customerId": customer_id,
                "since": since.isoformat(),
            },
        )

        interactions = result.get("interactions", [])

        # Group by day
        daily_data = self._group_by_day(interactions, window_days)

        # Calculate totals
        total = len(interactions)
        inbound = sum(1 for i in interactions if i.get("direction") == "customer")
        outbound = total - inbound

        # Calculate channel breakdown
        channel_breakdown: dict[str, int] = defaultdict(int)
        for interaction in interactions:
            channel = interaction.get("channel", "unknown")
            channel_breakdown[channel] += 1

        # Calculate days since last interaction
        days_since_last = self._days_since_last_interaction(interactions)

        # Calculate weekly average
        weeks = max(window_days / 7, 1)
        avg_weekly = total / weeks

        # Analyze direction
        direction = self._analyze_direction(daily_data, days_since_last)

        # Calculate confidence
        confidence = self._calculate_confidence(interactions, window_days)

        # Generate summary
        summary = self._generate_summary(
            direction=direction,
            total=total,
            inbound=inbound,
            outbound=outbound,
            days_since_last=days_since_last,
            window_days=window_days,
        )

        logger.info(
            "engagement_trend_computed",
            customer_id=customer_id,
            window_days=window_days,
            interaction_count=total,
            direction=direction.value,
            confidence=confidence,
        )

        return EngagementTrend(
            direction=direction,
            confidence=confidence,
            summary=summary,
            total_interactions=total,
            inbound_count=inbound,
            outbound_count=outbound,
            daily_data=daily_data,
            days_since_last_interaction=days_since_last,
            average_weekly_interactions=round(avg_weekly, 1),
            channel_breakdown=dict(channel_breakdown),
            window_days=window_days,
        )

    async def compare_periods(
        self,
        customer_id: str,
        current_days: int = 7,
        previous_days: int = 7
    ) -> EngagementComparison:
        """
        Compare engagement between current and previous periods.

        Useful for detecting recent engagement shifts.

        Args:
            customer_id: Customer UUID string
            current_days: Days in current period
            previous_days: Days in previous period

        Returns:
            EngagementComparison with deltas and interpretation
        """
        now = datetime.now(timezone.utc)

        # Fetch all interactions for both periods
        total_days = current_days + previous_days
        since = now - timedelta(days=total_days)

        result = await self.dc.execute_query(
            "GetInteractionsForEngagementTrend",
            {
                "workspaceId": self.workspace_id,
                "customerId": customer_id,
                "since": since.isoformat(),
            },
        )

        interactions = result.get("interactions", [])

        # Split into current and previous periods
        current_cutoff = now - timedelta(days=current_days)

        current_count = 0
        previous_count = 0

        for interaction in interactions:
            occurred_at_str = interaction.get("occurredAt", "")
            try:
                occurred_at = datetime.fromisoformat(occurred_at_str.replace('Z', '+00:00'))
                if occurred_at >= current_cutoff:
                    current_count += 1
                else:
                    previous_count += 1
            except (ValueError, AttributeError):
                pass

        delta = current_count - previous_count

        # Calculate percent change
        if previous_count > 0:
            percent_change = round((delta / previous_count) * 100, 1)
        else:
            percent_change = None if current_count == 0 else 100.0

        # Generate interpretation
        interpretation = self._interpret_comparison(
            current_count=current_count,
            previous_count=previous_count,
            delta=delta,
        )

        logger.info(
            "engagement_period_comparison",
            customer_id=customer_id,
            current_count=current_count,
            previous_count=previous_count,
            delta=delta,
            interpretation=interpretation,
        )

        return EngagementComparison(
            current_count=current_count,
            previous_count=previous_count,
            delta=delta,
            percent_change=percent_change,
            interpretation=interpretation,
        )

    def _group_by_day(
        self,
        interactions: list[dict],
        window_days: int
    ) -> list[DailyEngagement]:
        """
        Group interactions by day and fill in gaps.

        Returns a list of DailyEngagement for each day in the window,
        even if there are no interactions that day (for sparkline display).
        """
        # Initialize all days in the window
        now = datetime.now(timezone.utc)
        daily_map: dict[str, DailyEngagement] = {}

        for i in range(window_days):
            day = now - timedelta(days=window_days - 1 - i)
            date_str = day.strftime("%Y-%m-%d")
            daily_map[date_str] = DailyEngagement(
                date=date_str,
                total=0,
                inbound=0,
                outbound=0,
                channels=[],
            )

        # Populate with actual interactions
        for interaction in interactions:
            occurred_at_str = interaction.get("occurredAt", "")
            try:
                occurred_at = datetime.fromisoformat(occurred_at_str.replace('Z', '+00:00'))
                date_str = occurred_at.strftime("%Y-%m-%d")

                if date_str in daily_map:
                    daily = daily_map[date_str]
                    daily.total += 1

                    direction = interaction.get("direction", "")
                    if direction == "customer":
                        daily.inbound += 1
                    else:
                        daily.outbound += 1

                    channel = interaction.get("channel", "unknown")
                    if channel not in daily.channels:
                        daily.channels.append(channel)
            except (ValueError, AttributeError):
                pass

        # Return sorted by date
        return [daily_map[k] for k in sorted(daily_map.keys())]

    def _days_since_last_interaction(self, interactions: list[dict]) -> int | None:
        """Calculate days since the most recent interaction."""
        if not interactions:
            return None

        now = datetime.now(timezone.utc)
        most_recent = None

        for interaction in interactions:
            occurred_at_str = interaction.get("occurredAt", "")
            try:
                occurred_at = datetime.fromisoformat(occurred_at_str.replace('Z', '+00:00'))
                if most_recent is None or occurred_at > most_recent:
                    most_recent = occurred_at
            except (ValueError, AttributeError):
                pass

        if most_recent is None:
            return None

        return (now - most_recent).days

    def _analyze_direction(
        self,
        daily_data: list[DailyEngagement],
        days_since_last: int | None
    ) -> EngagementDirection:
        """
        Analyze trajectory of engagement over time.

        Uses a simple approach:
        - If no activity in 14+ days: going_dark
        - Compare first half vs second half of window
        - Determine direction based on change
        """
        # Check for going dark
        if days_since_last is not None and days_since_last >= 14:
            return EngagementDirection.GOING_DARK

        if len(daily_data) < 2:
            return EngagementDirection.STABLE

        # Split into first half and second half
        midpoint = len(daily_data) // 2
        first_half = daily_data[:midpoint]
        second_half = daily_data[midpoint:]

        first_total = sum(d.total for d in first_half)
        second_total = sum(d.total for d in second_half)

        # Normalize by number of days in each half
        first_avg = first_total / len(first_half) if first_half else 0
        second_avg = second_total / len(second_half) if second_half else 0

        # Threshold for determining direction
        if first_avg == 0 and second_avg == 0:
            return EngagementDirection.STABLE

        if first_avg == 0:
            return EngagementDirection.INCREASING

        ratio = second_avg / first_avg

        if ratio >= 1.3:
            return EngagementDirection.INCREASING
        elif ratio <= 0.7:
            return EngagementDirection.DECREASING
        else:
            return EngagementDirection.STABLE

    def _calculate_confidence(
        self,
        interactions: list[dict],
        window_days: int
    ) -> float:
        """
        Calculate confidence in trend based on data quality.

        Higher confidence when:
        - More interactions available
        - Interactions spread across time window
        """
        if not interactions:
            return 0.0

        # Base confidence on interaction count
        count_factor = min(len(interactions) / 10, 1.0)  # Max out at 10 interactions

        # Check temporal spread
        if len(interactions) >= 2:
            dates = set()
            for interaction in interactions:
                occurred_at_str = interaction.get("occurredAt", "")
                try:
                    occurred_at = datetime.fromisoformat(occurred_at_str.replace('Z', '+00:00'))
                    dates.add(occurred_at.strftime("%Y-%m-%d"))
                except (ValueError, AttributeError):
                    pass

            # How many unique days have interactions?
            spread_factor = min(len(dates) / (window_days * 0.3), 1.0)
        else:
            spread_factor = 0.3

        # Combine factors
        confidence = (count_factor * 0.6) + (spread_factor * 0.4)

        return round(confidence, 2)

    def _generate_summary(
        self,
        direction: EngagementDirection,
        total: int,
        inbound: int,
        outbound: int,
        days_since_last: int | None,
        window_days: int,
    ) -> str:
        """
        Generate human-readable summary of engagement trend.
        """
        if total == 0:
            return f"No interactions in the last {window_days} days"

        # Direction text
        direction_map = {
            EngagementDirection.INCREASING: "Engagement increasing",
            EngagementDirection.STABLE: "Engagement stable",
            EngagementDirection.DECREASING: "Engagement declining",
            EngagementDirection.GOING_DARK: "Customer going dark",
        }
        base = direction_map.get(direction, "Engagement stable")

        # Activity summary
        parts = [f"{total} interactions"]
        if inbound > 0 and outbound > 0:
            parts.append(f"{inbound} from them, {outbound} from us")
        elif inbound > 0:
            parts.append("all customer-initiated")
        elif outbound > 0:
            parts.append("all us-initiated")

        activity_summary = ", ".join(parts)

        # Last contact
        if days_since_last is not None and days_since_last > 0:
            last_contact = f"Last contact {days_since_last} day{'s' if days_since_last != 1 else ''} ago"
            return f"{base}: {activity_summary}. {last_contact}."

        return f"{base}: {activity_summary} in last {window_days} days."

    def _interpret_comparison(
        self,
        current_count: int,
        previous_count: int,
        delta: int,
    ) -> str:
        """
        Generate interpretation of period-over-period comparison.
        """
        if current_count == 0 and previous_count == 0:
            return "No activity in either period"

        if current_count == 0:
            return "Activity dropped to zero"

        if previous_count == 0:
            return "New activity this period"

        if delta > 0:
            if delta >= 3:
                return "Engagement surging"
            return "Engagement increasing"
        elif delta < 0:
            if delta <= -3:
                return "Engagement dropping significantly"
            return "Engagement declining"
        else:
            return "Engagement stable"


async def get_customer_engagement_summary(
    customer_id: str,
    workspace_id: str,
) -> dict:
    """
    Convenience function to get a quick engagement summary for a customer.

    Returns a dict suitable for inclusion in API responses or UI display.
    """
    service = EngagementTrendService(workspace_id=workspace_id)

    trend = await service.get_engagement_trend(customer_id, window_days=30)
    comparison = await service.compare_periods(customer_id, current_days=7, previous_days=7)

    return {
        "direction": trend.direction.value,
        "confidence": trend.confidence,
        "summary": trend.summary,
        "total_interactions_30d": trend.total_interactions,
        "inbound_count_30d": trend.inbound_count,
        "outbound_count_30d": trend.outbound_count,
        "days_since_last_interaction": trend.days_since_last_interaction,
        "average_weekly_interactions": trend.average_weekly_interactions,
        "channel_breakdown": trend.channel_breakdown,
        "daily_totals": [d.total for d in trend.daily_data],  # For sparkline
        "week_over_week": {
            "current": comparison.current_count,
            "previous": comparison.previous_count,
            "delta": comparison.delta,
            "percent_change": comparison.percent_change,
            "interpretation": comparison.interpretation,
        }
    }

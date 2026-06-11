"""
Sentiment Trend Service

Analyzes sentiment trends from signal history to provide insight into
customer relationship trajectory. Computes trends on-demand from existing
signal data - no additional tables required.

Used by:
- HealthScoringService to enrich health reasons with trend context
- Sidekick UI to show sentiment indicators
- Today Queue to surface sentiment shift alerts
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal
from enum import Enum
from collections import defaultdict

from db.dataconnect_client import DataConnectClient, get_dataconnect_client
from core.logging import get_logger

logger = get_logger("SentimentTrendService")


class TrendDirection(str, Enum):
    """Direction of sentiment trend over time."""
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"


@dataclass
class SentimentSnapshot:
    """Point-in-time sentiment reading from a signal."""
    date: datetime
    state: Literal["ok", "warn", "risk"]
    signal_id: str
    sentence: str | None
    evidence: str | None


@dataclass
class SentimentTrend:
    """Result of sentiment trend analysis."""
    current_state: Literal["ok", "warn", "risk"] | None
    direction: TrendDirection
    confidence: float  # 0.0-1.0 based on data quality
    snapshots: list[SentimentSnapshot]
    summary: str  # Human-readable summary
    negative_count: int
    positive_count: int
    window_days: int
    # Gap-filled daily sentiment scores (0.0-1.0), oldest->newest, one per day
    # in the window. Empty days carry forward the last known state; leading days
    # before the first signal default to 0.5 (neutral). Powers the RightRail sparkline.
    daily_scores: list[float] = field(default_factory=list)


@dataclass
class PeriodComparison:
    """Comparison of sentiment between two time periods."""
    current_negative_count: int
    current_positive_count: int
    previous_negative_count: int
    previous_positive_count: int
    delta_negative: int
    delta_positive: int
    interpretation: str


class SentimentTrendService:
    """
    Analyzes sentiment trends from signal history.

    Computes trends on-demand from existing Signal records.
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

    async def get_sentiment_trend(
        self,
        customer_id: str,
        window_days: int = 30
    ) -> SentimentTrend:
        """
        Compute sentiment trend for a customer over time window.

        Algorithm:
        1. Fetch sentiment signals from last N days
        2. Group by week
        3. Analyze trajectory (improving/stable/declining)
        4. Return structured trend with confidence

        Args:
            customer_id: Customer UUID string
            window_days: Number of days to analyze

        Returns:
            SentimentTrend with direction, confidence, and summary
        """
        since = datetime.now(timezone.utc) - timedelta(days=window_days)

        # Fetch sentiment signals
        result = await self.dc.execute_query(
            "GetSentimentSignalsForTrend",
            {
                "workspaceId": self.workspace_id,
                "customerId": customer_id,
                "since": since.isoformat(),
            },
        )

        signals = result.get("signals", [])

        # Convert to snapshots
        snapshots = []
        for signal in signals:
            generated_at_str = signal.get("generatedAt", "")
            try:
                generated_at = datetime.fromisoformat(generated_at_str.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                generated_at = datetime.now(timezone.utc)

            snapshots.append(SentimentSnapshot(
                date=generated_at,
                state=signal.get("state", "ok"),
                signal_id=signal.get("id", ""),
                sentence=signal.get("sentence"),
                evidence=signal.get("evidenceText"),
            ))

        # Count by state
        negative_count = sum(1 for s in snapshots if s.state == "risk")
        positive_count = sum(1 for s in snapshots if s.state == "ok")
        warn_count = sum(1 for s in snapshots if s.state == "warn")

        # Determine current state (from most recent signal)
        current_state = snapshots[-1].state if snapshots else None

        # Analyze trend direction
        direction = self._analyze_direction(snapshots, window_days)

        # Calculate confidence based on data quality
        confidence = self._calculate_confidence(snapshots, window_days)

        # Generate summary
        summary = self._generate_summary(
            direction=direction,
            negative_count=negative_count,
            positive_count=positive_count,
            warn_count=warn_count,
            window_days=window_days,
            snapshots=snapshots,
        )

        # Build gap-filled daily scores for sparkline visualization
        daily_scores = self._build_daily_scores(snapshots, window_days)

        logger.info(
            "sentiment_trend_computed",
            customer_id=customer_id,
            window_days=window_days,
            signal_count=len(snapshots),
            direction=direction.value,
            confidence=confidence,
        )

        return SentimentTrend(
            current_state=current_state,
            direction=direction,
            confidence=confidence,
            snapshots=snapshots,
            summary=summary,
            negative_count=negative_count,
            positive_count=positive_count,
            window_days=window_days,
            daily_scores=daily_scores,
        )

    async def compare_periods(
        self,
        customer_id: str,
        current_days: int = 7,
        previous_days: int = 7
    ) -> PeriodComparison:
        """
        Compare sentiment between current and previous periods.

        Useful for detecting recent sentiment shifts.

        Args:
            customer_id: Customer UUID string
            current_days: Days in current period
            previous_days: Days in previous period

        Returns:
            PeriodComparison with deltas and interpretation
        """
        now = datetime.now(timezone.utc)

        current_since = now - timedelta(days=current_days)
        previous_until = current_since
        previous_since = previous_until - timedelta(days=previous_days)

        # GetSentimentSignalsForTrend filters generatedAt >= since, so a single
        # query at the older `previous_since` bound already returns every signal
        # in BOTH periods. Fetch once and split client-side rather than issuing
        # two overlapping round-trips for the same rows.
        result = await self.dc.execute_query(
            "GetSentimentSignalsForTrend",
            {
                "workspaceId": self.workspace_id,
                "customerId": customer_id,
                "since": previous_since.isoformat(),
            },
        )
        all_signals = result.get("signals", [])

        # Partition into current (>= previous_until) and previous (< previous_until).
        current_signals = []
        previous_signals = []
        for signal in all_signals:
            generated_at_str = signal.get("generatedAt", "")
            try:
                generated_at = datetime.fromisoformat(generated_at_str.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                continue
            if generated_at >= previous_until:
                current_signals.append(signal)
            else:
                previous_signals.append(signal)

        # Count negatives and positives
        current_negative = sum(1 for s in current_signals if s.get("state") == "risk")
        current_positive = sum(1 for s in current_signals if s.get("state") == "ok")
        previous_negative = sum(1 for s in previous_signals if s.get("state") == "risk")
        previous_positive = sum(1 for s in previous_signals if s.get("state") == "ok")

        delta_negative = current_negative - previous_negative
        delta_positive = current_positive - previous_positive

        # Generate interpretation
        interpretation = self._interpret_comparison(
            delta_negative=delta_negative,
            delta_positive=delta_positive,
            current_negative=current_negative,
            current_positive=current_positive,
        )

        logger.info(
            "sentiment_period_comparison",
            customer_id=customer_id,
            current_negative=current_negative,
            previous_negative=previous_negative,
            delta_negative=delta_negative,
            interpretation=interpretation,
        )

        return PeriodComparison(
            current_negative_count=current_negative,
            current_positive_count=current_positive,
            previous_negative_count=previous_negative,
            previous_positive_count=previous_positive,
            delta_negative=delta_negative,
            delta_positive=delta_positive,
            interpretation=interpretation,
        )

    @staticmethod
    def _state_score(state: str) -> float:
        """Map a sentiment state to a 0.0-1.0 score (risk=0, warn=0.5, ok=1)."""
        return {"ok": 1.0, "warn": 0.5, "risk": 0.0}.get(state, 0.5)

    def _build_daily_scores(
        self,
        snapshots: list[SentimentSnapshot],
        window_days: int,
    ) -> list[float]:
        """
        Build a gap-filled daily sentiment series for sparkline visualization.

        Sentiment signals are sparse and event-driven, so naive per-signal arrays
        can't be plotted on a time axis. This buckets signals by calendar day
        (UTC), averages multiple signals within a day, and carries the last known
        score forward across empty days (a customer stays at-risk on the days
        between two risk signals). Leading days before the first signal default to
        0.5 (neutral - no data yet).

        Returns exactly `window_days` floats (0.0-1.0), oldest -> newest.
        Returns [] when there are no signals (UI then hides the sparkline rather
        than fabricating a line).
        """
        if not snapshots:
            return []

        now = datetime.now(timezone.utc)

        # Ordered day keys across the window, oldest -> newest.
        day_keys = [
            (now - timedelta(days=window_days - 1 - i)).strftime("%Y-%m-%d")
            for i in range(window_days)
        ]
        valid_keys = set(day_keys)

        # Bucket snapshot scores by day; average signals landing on the same day.
        scores_by_day: dict[str, list[float]] = defaultdict(list)
        for snap in snapshots:
            day = snap.date
            if day.tzinfo is None:
                day = day.replace(tzinfo=timezone.utc)
            key = day.astimezone(timezone.utc).strftime("%Y-%m-%d")
            if key in valid_keys:
                scores_by_day[key].append(self._state_score(snap.state))

        # Walk the window forward, carrying the last known score across gaps.
        daily: list[float] = []
        last: float | None = None
        for key in day_keys:
            if key in scores_by_day:
                day_scores = scores_by_day[key]
                last = sum(day_scores) / len(day_scores)
            daily.append(round(last if last is not None else 0.5, 3))

        return daily

    def _analyze_direction(
        self,
        snapshots: list[SentimentSnapshot],
        window_days: int
    ) -> TrendDirection:
        """
        Analyze trajectory of sentiment over time.

        Uses a simple weighted approach:
        - Split window into halves
        - Compare average sentiment in each half
        - Determine direction based on change
        """
        if len(snapshots) < 2:
            return TrendDirection.STABLE

        # Split into first half and second half
        midpoint = len(snapshots) // 2
        first_half = snapshots[:midpoint] if midpoint > 0 else []
        second_half = snapshots[midpoint:]

        if not first_half or not second_half:
            return TrendDirection.STABLE

        # Use the shared 0.0-1.0 state score (risk=0, warn=0.5, ok=1) instead of a
        # second, divergent mapping. The ±0.15 threshold mirrors the prior ±0.3 on
        # the old -1..1 scale, whose span was twice as wide, so classifications are
        # unchanged.
        first_avg = sum(self._state_score(s.state) for s in first_half) / len(first_half)
        second_avg = sum(self._state_score(s.state) for s in second_half) / len(second_half)

        diff = second_avg - first_avg

        if diff > 0.15:
            return TrendDirection.IMPROVING
        elif diff < -0.15:
            return TrendDirection.DECLINING
        else:
            return TrendDirection.STABLE

    def _calculate_confidence(
        self,
        snapshots: list[SentimentSnapshot],
        window_days: int
    ) -> float:
        """
        Calculate confidence in trend based on data quality.

        Higher confidence when:
        - More signals available
        - Signals spread across time window
        - Consistent pattern
        """
        if not snapshots:
            return 0.0

        # Base confidence on signal count (more = better, up to a point)
        count_factor = min(len(snapshots) / 5, 1.0)  # Max out at 5 signals

        # Check temporal spread (signals should be distributed)
        if len(snapshots) >= 2:
            first_date = snapshots[0].date
            last_date = snapshots[-1].date
            actual_span = (last_date - first_date).days
            expected_span = window_days * 0.5  # Expect at least half the window
            spread_factor = min(actual_span / expected_span, 1.0) if expected_span > 0 else 0.5
        else:
            spread_factor = 0.3

        # Combine factors
        confidence = (count_factor * 0.6) + (spread_factor * 0.4)

        return round(confidence, 2)

    def _generate_summary(
        self,
        direction: TrendDirection,
        negative_count: int,
        positive_count: int,
        warn_count: int,
        window_days: int,
        snapshots: list[SentimentSnapshot],
    ) -> str:
        """
        Generate human-readable summary of sentiment trend.
        """
        total = negative_count + positive_count + warn_count

        if total == 0:
            return f"No sentiment signals in the last {window_days} days"

        # Build summary based on direction
        if direction == TrendDirection.IMPROVING:
            base = "Sentiment improving"
        elif direction == TrendDirection.DECLINING:
            base = "Sentiment declining"
        else:
            base = "Sentiment stable"

        # Add signal counts
        parts = []
        if negative_count > 0:
            parts.append(f"{negative_count} frustrated")
        if warn_count > 0:
            parts.append(f"{warn_count} concerned")
        if positive_count > 0:
            parts.append(f"{positive_count} positive")

        signal_summary = ", ".join(parts) if parts else "no signals"

        # Add most recent context if available
        recent_context = ""
        if snapshots:
            most_recent = snapshots[-1]
            if most_recent.sentence:
                recent_context = f" Most recent: {most_recent.sentence[:60]}..."

        return f"{base}: {signal_summary} in last {window_days} days.{recent_context}"

    def _interpret_comparison(
        self,
        delta_negative: int,
        delta_positive: int,
        current_negative: int,
        current_positive: int,
    ) -> str:
        """
        Generate interpretation of period-over-period comparison.
        """
        if delta_negative > 0 and delta_positive <= 0:
            if delta_negative >= 2:
                return "Sentiment deteriorating significantly"
            return "Sentiment declining"
        elif delta_negative < 0 and delta_positive >= 0:
            if delta_positive >= 2:
                return "Sentiment improving significantly"
            return "Sentiment improving"
        elif delta_negative == 0 and delta_positive == 0:
            if current_negative > current_positive:
                return "Sentiment remains negative"
            elif current_positive > current_negative:
                return "Sentiment remains positive"
            return "Sentiment stable"
        elif delta_negative > 0 and delta_positive > 0:
            return "Mixed signals - both positive and negative sentiment increasing"
        else:
            return "Sentiment stable"


async def get_customer_sentiment_summary(
    customer_id: str,
    workspace_id: str,
) -> dict:
    """
    Convenience function to get a quick sentiment summary for a customer.

    Returns a dict suitable for inclusion in API responses or UI display.
    """
    service = SentimentTrendService(workspace_id=workspace_id)

    trend = await service.get_sentiment_trend(customer_id, window_days=30)
    comparison = await service.compare_periods(customer_id, current_days=7, previous_days=7)

    return {
        "current_state": trend.current_state,
        "direction": trend.direction.value,
        "confidence": trend.confidence,
        "summary": trend.summary,
        "negative_count_30d": trend.negative_count,
        "positive_count_30d": trend.positive_count,
        "week_over_week": {
            "delta_negative": comparison.delta_negative,
            "delta_positive": comparison.delta_positive,
            "interpretation": comparison.interpretation,
        }
    }

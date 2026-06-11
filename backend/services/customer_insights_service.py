"""
Customer Insights Service

Unified service that computes customer sentiment + engagement insights
and writes to Firestore for real-time subscriptions.

This service wraps:
- SentimentTrendService (sentiment_trend_service.py)
- EngagementTrendService (engagement_trend_service.py)

And writes to:
- workspaces/{wsId}/customer_insights/{custId}
- workspaces/{wsId}/portfolio_snapshot

Used by:
- RightRail component (via useCustomerInsights hook)
- SidekickMap component (via usePortfolioInsights hook)
- Signal classification (to trigger updates)
"""

import asyncio
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Literal
from collections import Counter

from db.dataconnect_client import DataConnectClient, get_dataconnect_client
from services.sentiment_trend_service import SentimentTrendService, SentimentTrend, TrendDirection
from services.engagement_trend_service import EngagementTrendService, EngagementTrend, EngagementDirection
from services.firestore_service import get_firestore_service, _normalize_uuid
from google.cloud.firestore_v1 import SERVER_TIMESTAMP
from core.logging import get_logger

logger = get_logger("CustomerInsightsService")


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class CustomerInsight:
    """Complete customer insight for UI display and Firestore storage."""

    # Identity
    customer_id: str
    customer_name: str
    customer_slug: str

    # Coordinates for Sidekick Map (both 0-1 normalized)
    engagement_score: float  # X-axis: 0 = silent, 1 = highly engaged
    sentiment_score: float   # Y-axis: 0 = frustrated, 1 = happy

    # Trend directions (for arrows on the map)
    engagement_direction: str  # increasing | stable | decreasing | going_dark
    sentiment_direction: str   # improving | stable | declining

    # Derived classification
    quadrant: str  # healthy | quiet | going_dark | escalating | slipping
    priority: str  # high | medium | low
    alert_reason: str | None

    # Sparkline data (30 daily values)
    engagement_sparkline: list[int] = field(default_factory=list)
    sentiment_sparkline: list[float] = field(default_factory=list)

    # Raw metrics
    days_since_last_interaction: int | None = None
    negative_signals_30d: int = 0
    positive_signals_30d: int = 0
    total_interactions_30d: int = 0
    inbound_interactions_30d: int = 0
    outbound_interactions_30d: int = 0

    # Week-over-week
    engagement_wow_current: int = 0
    engagement_wow_previous: int = 0
    engagement_wow_delta: int = 0
    engagement_wow_percent: float | None = None
    sentiment_wow_delta_negative: int = 0
    sentiment_wow_delta_positive: int = 0
    sentiment_wow_interpretation: str = ""

    # Metadata
    confidence: float = 0.0

    def to_firestore_dict(self) -> dict:
        """Convert to dict for Firestore, adding server timestamp."""
        data = asdict(self)
        data["last_computed"] = SERVER_TIMESTAMP
        return data


@dataclass
class PortfolioCustomer:
    """Customer position in the portfolio map."""
    id: str
    name: str
    slug: str
    x: float  # engagement_score (0-1)
    y: float  # sentiment_score (0-1)
    quadrant: str
    priority: str
    alert_reason: str | None
    trend_x: str  # up | down | stable
    trend_y: str  # up | down | stable


@dataclass
class PortfolioSnapshot:
    """Aggregated portfolio-level metrics."""

    # Map data points
    customers: list[dict] = field(default_factory=list)

    # Pre-sorted priority list
    priority_list: list[dict] = field(default_factory=list)

    # Summary counts
    healthy_count: int = 0
    quiet_count: int = 0
    going_dark_count: int = 0
    escalating_count: int = 0
    slipping_count: int = 0

    # Metadata
    customer_count: int = 0

    def to_firestore_dict(self) -> dict:
        """Convert to dict for Firestore, adding server timestamp."""
        data = asdict(self)
        data["last_computed"] = SERVER_TIMESTAMP
        return data


# =============================================================================
# Service
# =============================================================================


class CustomerInsightsService:
    """
    Computes customer insights and writes to Firestore for real-time subscriptions.

    Core Flow:
    1. Call SentimentTrendService + EngagementTrendService
    2. Normalize scores to 0-1
    3. Classify into quadrants
    4. Write to Firestore
    5. Update portfolio snapshot
    """

    def __init__(
        self,
        dc: DataConnectClient | None = None,
        workspace_id: str | None = None,
    ):
        self.dc = dc or get_dataconnect_client()
        self.workspace_id = workspace_id
        self.sentiment_service = SentimentTrendService(dc=self.dc, workspace_id=workspace_id)
        self.engagement_service = EngagementTrendService(dc=self.dc, workspace_id=workspace_id)
        self.firestore = get_firestore_service()

    async def update_customer_insight(
        self,
        customer_id: str,
        update_portfolio: bool = True,
    ) -> CustomerInsight:
        """
        Compute and cache a single customer's insight.

        Called when signals or interactions change.

        Args:
            customer_id: Customer UUID
            update_portfolio: Whether to update portfolio snapshot after

        Returns:
            CustomerInsight with all computed data
        """
        logger.info(
            "computing_customer_insight",
            customer_id=customer_id,
            workspace_id=self.workspace_id,
        )

        # Get customer info
        customer = await self._get_customer(customer_id)
        customer_name = customer.get("name", "") if customer else ""
        customer_slug = customer.get("slug", "") if customer else ""

        # Compute both trends in parallel
        sentiment, engagement = await asyncio.gather(
            self._get_sentiment_safe(customer_id),
            self._get_engagement_safe(customer_id),
            return_exceptions=True,
        )

        # Handle exceptions
        if isinstance(sentiment, Exception):
            logger.warning("sentiment_trend_failed", customer_id=customer_id, error=str(sentiment))
            sentiment = None
        if isinstance(engagement, Exception):
            logger.warning("engagement_trend_failed", customer_id=customer_id, error=str(engagement))
            engagement = None

        # Get week-over-week comparisons
        sentiment_wow, engagement_wow = await asyncio.gather(
            self._get_sentiment_wow_safe(customer_id),
            self._get_engagement_wow_safe(customer_id),
            return_exceptions=True,
        )

        if isinstance(sentiment_wow, Exception):
            sentiment_wow = None
        if isinstance(engagement_wow, Exception):
            engagement_wow = None

        # Normalize to 0-1 scores
        engagement_score = self._normalize_engagement(engagement) if engagement else 0.5
        sentiment_score = self._normalize_sentiment(sentiment) if sentiment else 0.5

        # Get directions
        engagement_direction = engagement.direction.value if engagement else "stable"
        sentiment_direction = sentiment.direction.value if sentiment else "stable"

        # Classify quadrant
        quadrant = self._classify_quadrant(
            engagement_score,
            sentiment_score,
            engagement_direction,
            sentiment_direction,
        )

        # Compute priority and alert reason
        priority, alert_reason = self._compute_priority(
            quadrant,
            sentiment,
            engagement,
        )

        # Build sparkline data (both gap-filled, 30 daily values, oldest->newest)
        engagement_sparkline = [d.total for d in engagement.daily_data] if engagement else []
        sentiment_sparkline = sentiment.daily_scores if sentiment else []

        # Build insight
        insight = CustomerInsight(
            customer_id=customer_id,
            customer_name=customer_name,
            customer_slug=customer_slug,
            engagement_score=engagement_score,
            sentiment_score=sentiment_score,
            engagement_direction=engagement_direction,
            sentiment_direction=sentiment_direction,
            quadrant=quadrant,
            priority=priority,
            alert_reason=alert_reason,
            engagement_sparkline=engagement_sparkline,
            sentiment_sparkline=sentiment_sparkline,
            days_since_last_interaction=engagement.days_since_last_interaction if engagement else None,
            negative_signals_30d=sentiment.negative_count if sentiment else 0,
            positive_signals_30d=sentiment.positive_count if sentiment else 0,
            total_interactions_30d=engagement.total_interactions if engagement else 0,
            inbound_interactions_30d=engagement.inbound_count if engagement else 0,
            outbound_interactions_30d=engagement.outbound_count if engagement else 0,
            engagement_wow_current=engagement_wow.current_count if engagement_wow else 0,
            engagement_wow_previous=engagement_wow.previous_count if engagement_wow else 0,
            engagement_wow_delta=engagement_wow.delta if engagement_wow else 0,
            engagement_wow_percent=engagement_wow.percent_change if engagement_wow else None,
            sentiment_wow_delta_negative=sentiment_wow.delta_negative if sentiment_wow else 0,
            sentiment_wow_delta_positive=sentiment_wow.delta_positive if sentiment_wow else 0,
            sentiment_wow_interpretation=sentiment_wow.interpretation if sentiment_wow else "",
            confidence=min(
                sentiment.confidence if sentiment else 0,
                engagement.confidence if engagement else 0,
            ),
        )

        # Write to Firestore
        await self._write_insight_to_firestore(insight)

        # Update portfolio snapshot
        if update_portfolio:
            await self.update_portfolio_snapshot()

        logger.info(
            "customer_insight_computed",
            customer_id=customer_id,
            quadrant=quadrant,
            priority=priority,
            engagement_score=engagement_score,
            sentiment_score=sentiment_score,
        )

        return insight

    async def update_portfolio_snapshot(self) -> PortfolioSnapshot:
        """
        Recompute the full portfolio snapshot from Firestore customer insights.

        Called after customer insight updates.
        """
        logger.info(
            "updating_portfolio_snapshot",
            workspace_id=self.workspace_id,
        )

        # Read all customer insights from Firestore
        try:
            normalized_ws_id = _normalize_uuid(self.workspace_id)
            insights_ref = self.firestore.db.collection('workspaces').document(
                normalized_ws_id
            ).collection('customer_insights')

            docs = insights_ref.stream()
            insights = [doc.to_dict() for doc in docs]
        except Exception as e:
            logger.error("portfolio_read_failed", error=str(e))
            insights = []

        # Build customer positions
        customers = []
        for ins in insights:
            customers.append({
                "id": ins.get("customer_id", ""),
                "name": ins.get("customer_name", ""),
                "slug": ins.get("customer_slug", ""),
                "x": ins.get("engagement_score", 0.5),
                "y": ins.get("sentiment_score", 0.5),
                "quadrant": ins.get("quadrant", "healthy"),
                "priority": ins.get("priority", "low"),
                "alertReason": ins.get("alert_reason"),
                "trendX": self._direction_to_trend(ins.get("engagement_direction", "stable")),
                "trendY": self._direction_to_trend(ins.get("sentiment_direction", "stable")),
            })

        # Build priority list (high priority customers)
        priority_list = [
            {
                "id": c["id"],
                "name": c["name"],
                "quadrant": c["quadrant"],
                "reason": c["alertReason"] or c["quadrant"].replace("_", " ").title(),
            }
            for c in customers
            if c["priority"] == "high"
        ]

        # Count by quadrant
        counts = Counter(c["quadrant"] for c in customers)

        # Build snapshot
        snapshot = PortfolioSnapshot(
            customers=customers,
            priority_list=priority_list,
            healthy_count=counts.get("healthy", 0),
            quiet_count=counts.get("quiet", 0),
            going_dark_count=counts.get("going_dark", 0),
            escalating_count=counts.get("escalating", 0),
            slipping_count=counts.get("slipping", 0),
            customer_count=len(customers),
        )

        # Write to Firestore
        await self._write_portfolio_to_firestore(snapshot)

        logger.info(
            "portfolio_snapshot_updated",
            workspace_id=self.workspace_id,
            customer_count=len(customers),
            healthy=snapshot.healthy_count,
            at_risk=snapshot.going_dark_count + snapshot.escalating_count + snapshot.slipping_count,
        )

        return snapshot

    # =========================================================================
    # Private: Data Fetching
    # =========================================================================

    async def _get_customer(self, customer_id: str) -> dict | None:
        """Get customer info from DataConnect."""
        try:
            return await self.dc.get_customer(customer_id)
        except Exception as e:
            logger.warning("get_customer_failed", customer_id=customer_id, error=str(e))
            return None

    async def _get_sentiment_safe(self, customer_id: str) -> SentimentTrend | None:
        """Get sentiment trend with error handling."""
        try:
            return await self.sentiment_service.get_sentiment_trend(customer_id, window_days=30)
        except Exception as e:
            raise e

    async def _get_engagement_safe(self, customer_id: str) -> EngagementTrend | None:
        """Get engagement trend with error handling."""
        try:
            return await self.engagement_service.get_engagement_trend(customer_id, window_days=30)
        except Exception as e:
            raise e

    async def _get_sentiment_wow_safe(self, customer_id: str):
        """Get sentiment week-over-week comparison."""
        try:
            return await self.sentiment_service.compare_periods(customer_id, current_days=7, previous_days=7)
        except Exception:
            return None

    async def _get_engagement_wow_safe(self, customer_id: str):
        """Get engagement week-over-week comparison."""
        try:
            return await self.engagement_service.compare_periods(customer_id, current_days=7, previous_days=7)
        except Exception:
            return None

    # =========================================================================
    # Private: Normalization
    # =========================================================================

    def _normalize_engagement(self, engagement: EngagementTrend) -> float:
        """
        Normalize engagement to 0-1 score.

        Factors:
        - Days since last interaction (0 = today, 30+ = cold)
        - Weekly average vs expected baseline
        - Direction trend
        """
        score = 0.5  # Start neutral

        # Days since last interaction (major factor)
        if engagement.days_since_last_interaction is not None:
            days = engagement.days_since_last_interaction
            if days == 0:
                score += 0.3
            elif days <= 3:
                score += 0.2
            elif days <= 7:
                score += 0.1
            elif days <= 14:
                score -= 0.1
            else:
                score -= 0.3

        # Weekly interaction rate
        if engagement.average_weekly_interactions >= 5:
            score += 0.15
        elif engagement.average_weekly_interactions >= 2:
            score += 0.05
        elif engagement.average_weekly_interactions < 1:
            score -= 0.1

        # Direction adjustment
        if engagement.direction == EngagementDirection.INCREASING:
            score += 0.1
        elif engagement.direction == EngagementDirection.DECREASING:
            score -= 0.1
        elif engagement.direction == EngagementDirection.GOING_DARK:
            score -= 0.2

        return max(0.0, min(1.0, score))

    def _normalize_sentiment(self, sentiment: SentimentTrend) -> float:
        """
        Normalize sentiment to 0-1 score.

        Factors:
        - Negative vs positive signal ratio
        - Current state
        - Direction trend
        """
        total = sentiment.negative_count + sentiment.positive_count

        if total == 0:
            return 0.5  # No data = neutral

        # Base score on ratio
        positive_ratio = sentiment.positive_count / total
        score = positive_ratio  # 0-1 based on ratio

        # Adjust for direction
        if sentiment.direction == TrendDirection.IMPROVING:
            score = min(1.0, score + 0.1)
        elif sentiment.direction == TrendDirection.DECLINING:
            score = max(0.0, score - 0.1)

        # Current state adjustment
        if sentiment.current_state == "risk":
            score = max(0.0, score - 0.15)
        elif sentiment.current_state == "ok":
            score = min(1.0, score + 0.1)

        return max(0.0, min(1.0, score))

    # =========================================================================
    # Private: Classification
    # =========================================================================

    def _classify_quadrant(
        self,
        engagement: float,
        sentiment: float,
        eng_direction: str,
        sent_direction: str,
    ) -> str:
        """
        Classify into quadrant based on scores and directions.

        Quadrants:
        - healthy: high engagement, high sentiment
        - quiet: low engagement, high sentiment (not talking but happy)
        - going_dark: low engagement, low sentiment (silent and unhappy)
        - escalating: high engagement, low sentiment (talking a lot, unhappy)
        - slipping: engagement down, sentiment down (divergence pattern)
        """
        # Check for divergence first (most important signal)
        if eng_direction == "increasing" and sent_direction == "declining":
            return "escalating"  # Getting angrier, talking more

        if eng_direction == "decreasing" and sent_direction == "declining":
            return "slipping"  # Disengaging and unhappy

        # Quadrant based on scores
        high_engagement = engagement >= 0.5
        high_sentiment = sentiment >= 0.5

        if high_engagement and high_sentiment:
            return "healthy"
        elif not high_engagement and high_sentiment:
            return "quiet"
        elif not high_engagement and not high_sentiment:
            return "going_dark"
        else:  # high_engagement and not high_sentiment
            return "escalating"

    def _compute_priority(
        self,
        quadrant: str,
        sentiment: SentimentTrend | None,
        engagement: EngagementTrend | None,
    ) -> tuple[str, str | None]:
        """
        Compute priority level and alert reason.

        Priority:
        - high: needs immediate attention
        - medium: worth monitoring
        - low: healthy, no action needed
        """
        # High priority conditions
        if quadrant == "escalating":
            return ("high", "Engagement climbing while sentiment falls")

        if quadrant == "going_dark":
            days = engagement.days_since_last_interaction if engagement else None
            if days and days > 14:
                return ("high", f"No contact in {days} days, sentiment negative")
            return ("high", "Going silent with negative sentiment")

        if quadrant == "slipping":
            return ("high", "Disengaging with declining sentiment")

        if sentiment and sentiment.negative_count >= 5:
            return ("medium", f"{sentiment.negative_count} negative signals in 30 days")

        if quadrant == "quiet":
            days = engagement.days_since_last_interaction if engagement else None
            if days and days > 14:
                return ("medium", f"No contact in {days} days")
            return ("low", None)

        # Healthy
        return ("low", None)

    def _direction_to_trend(self, direction: str) -> str:
        """Convert direction enum to simple trend indicator."""
        if direction in ("increasing", "improving"):
            return "up"
        elif direction in ("decreasing", "declining", "going_dark"):
            return "down"
        else:
            return "stable"

    # =========================================================================
    # Private: Firestore
    # =========================================================================

    async def _write_insight_to_firestore(self, insight: CustomerInsight) -> None:
        """Write customer insight to Firestore."""
        try:
            normalized_ws_id = _normalize_uuid(self.workspace_id)
            normalized_cust_id = _normalize_uuid(insight.customer_id)

            doc_ref = self.firestore.db.collection('workspaces').document(
                normalized_ws_id
            ).collection('customer_insights').document(normalized_cust_id)

            doc_ref.set(insight.to_firestore_dict())

            logger.debug(
                "insight_written_to_firestore",
                customer_id=insight.customer_id,
                workspace_id=self.workspace_id,
            )
        except Exception as e:
            logger.error(
                "insight_firestore_write_failed",
                customer_id=insight.customer_id,
                error=str(e),
            )
            # Don't raise - Firestore writes are best-effort

    async def _write_portfolio_to_firestore(self, snapshot: PortfolioSnapshot) -> None:
        """Write portfolio snapshot to Firestore."""
        try:
            normalized_ws_id = _normalize_uuid(self.workspace_id)

            doc_ref = self.firestore.db.collection('workspaces').document(
                normalized_ws_id
            ).collection('portfolio_snapshot').document('current')

            doc_ref.set(snapshot.to_firestore_dict())

            logger.debug(
                "portfolio_written_to_firestore",
                workspace_id=self.workspace_id,
                customer_count=snapshot.customer_count,
            )
        except Exception as e:
            logger.error(
                "portfolio_firestore_write_failed",
                workspace_id=self.workspace_id,
                error=str(e),
            )
            # Don't raise - Firestore writes are best-effort


# =============================================================================
# Convenience Functions
# =============================================================================


async def refresh_customer_insight(
    customer_id: str,
    workspace_id: str,
    update_portfolio: bool = True,
) -> CustomerInsight:
    """
    Convenience function to refresh a customer's insight.

    Used by signal classification, webhooks, and API endpoints.
    """
    service = CustomerInsightsService(workspace_id=workspace_id)
    return await service.update_customer_insight(
        customer_id=customer_id,
        update_portfolio=update_portfolio,
    )


async def refresh_all_customer_insights(workspace_id: str) -> int:
    """
    Refresh insights for all customers in a workspace.

    Used by bulk refresh endpoint and cron jobs.

    Returns:
        Number of customers updated.
    """
    dc = get_dataconnect_client()
    service = CustomerInsightsService(dc=dc, workspace_id=workspace_id)

    # Get all customers
    customers = await dc.get_customers(workspace_id)

    count = 0
    for customer in customers:
        try:
            await service.update_customer_insight(
                customer_id=customer["id"],
                update_portfolio=False,  # Batch update at end
            )
            count += 1
        except Exception as e:
            logger.error(
                "customer_insight_refresh_failed",
                customer_id=customer["id"],
                error=str(e),
            )

    # Update portfolio once at end
    await service.update_portfolio_snapshot()

    logger.info(
        "all_customer_insights_refreshed",
        workspace_id=workspace_id,
        count=count,
    )

    return count

"""
Customer Routes
FastAPI endpoints for customer-related operations (health scoring, etc.)
"""

from fastapi import APIRouter, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from middleware.auth import FirebaseUser, require_workspace_access
from core.logging import get_logger
from db.dataconnect_client import get_dataconnect_client
from services import HealthScoringService
from services.sentiment_trend_service import SentimentTrendService, TrendDirection
from services.engagement_trend_service import EngagementTrendService, EngagementDirection

router = APIRouter(prefix="/workspaces", tags=["customers"])
logger = get_logger("customer_routes")


# =============================================================================
# Request/Response Models
# =============================================================================


class CalculateHealthResponse(BaseModel):
    """Response from health calculation."""
    success: bool
    customer_id: str
    score: int
    health: str
    reason: str
    message: Optional[str] = None


class RecalculateAllHealthResponse(BaseModel):
    """Response from bulk health recalculation."""
    success: bool
    total: int
    updated: int
    failed: int
    errors: list[dict]


class WeekOverWeekComparison(BaseModel):
    """Week-over-week comparison data."""
    current: int
    previous: int
    delta: int
    percent_change: Optional[float] = None
    interpretation: str


class SentimentTrendResponse(BaseModel):
    """Sentiment trend data."""
    current_state: Optional[str] = None
    direction: str
    confidence: float
    summary: str
    negative_count_30d: int
    positive_count_30d: int
    daily_scores: list[float] = []
    week_over_week: WeekOverWeekComparison


class EngagementTrendResponse(BaseModel):
    """Engagement trend data."""
    direction: str
    confidence: float
    summary: str
    total_interactions_30d: int
    inbound_count_30d: int
    outbound_count_30d: int
    days_since_last_interaction: Optional[int] = None
    average_weekly_interactions: float
    channel_breakdown: dict[str, int]
    daily_totals: list[int]  # For sparkline visualization
    week_over_week: WeekOverWeekComparison


class CustomerTrendsResponse(BaseModel):
    """Combined sentiment and engagement trends for a customer."""
    success: bool
    customer_id: str
    sentiment: Optional[SentimentTrendResponse] = None
    engagement: Optional[EngagementTrendResponse] = None
    message: Optional[str] = None


# =============================================================================
# Health Scoring Endpoints
# =============================================================================


@router.post("/{workspace_id}/customers/{customer_id}/health/calculate")
async def calculate_customer_health(
    workspace_id: str,
    customer_id: str,
    background_tasks: BackgroundTasks,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> CalculateHealthResponse:
    """
    Calculate health score for a specific customer.

    Analyzes signals and stakeholder engagement to determine relationship health.
    Updates the customer's health fields in the database.
    """
    logger.info(
        "health_calculation_requested",
        workspace_id=workspace_id,
        customer_id=customer_id,
        user_id=user.uid,
    )

    try:
        dc = get_dataconnect_client()
        health_service = HealthScoringService(dc, workspace_id)

        # Calculate health score
        result = await health_service.calculate_health(
            customer_id,
            updated_by=f"user:{user.uid}",
        )

        logger.info(
            "health_calculation_completed",
            workspace_id=workspace_id,
            customer_id=customer_id,
            score=result.score,
            health=result.health,
        )

        return CalculateHealthResponse(
            success=True,
            customer_id=customer_id,
            score=result.score,
            health=result.health,
            reason=result.reason,
            message="Health score calculated successfully",
        )

    except Exception as e:
        logger.error(
            "health_calculation_failed",
            workspace_id=workspace_id,
            customer_id=customer_id,
            error=str(e),
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"Failed to calculate health: {str(e)}",
            },
        )


@router.post("/{workspace_id}/customers/health/recalculate")
async def recalculate_all_health(
    workspace_id: str,
    background_tasks: BackgroundTasks,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> RecalculateAllHealthResponse:
    """
    Recalculate health scores for all customers in the workspace.

    This is useful for:
    - After changing health scoring weights
    - Periodic bulk updates
    - Data migrations

    WARNING: This operation can be expensive for workspaces with many customers.
    Consider running it as a background task or during off-peak hours.
    """
    logger.info(
        "bulk_health_recalculation_requested",
        workspace_id=workspace_id,
        user_id=user.uid,
    )

    try:
        dc = get_dataconnect_client()
        health_service = HealthScoringService(dc, workspace_id)

        # Recalculate all customers
        results = await health_service.recalculate_all_customers()

        logger.info(
            "bulk_health_recalculation_completed",
            workspace_id=workspace_id,
            total=results["total"],
            updated=results["updated"],
            failed=results["failed"],
        )

        return RecalculateAllHealthResponse(
            success=True,
            total=results["total"],
            updated=results["updated"],
            failed=results["failed"],
            errors=results["errors"],
        )

    except Exception as e:
        logger.error(
            "bulk_health_recalculation_failed",
            workspace_id=workspace_id,
            error=str(e),
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"Failed to recalculate health scores: {str(e)}",
            },
        )


# =============================================================================
# Trend Analysis Endpoints
# =============================================================================


@router.get("/{workspace_id}/customers/{customer_id}/trends")
async def get_customer_trends(
    workspace_id: str,
    customer_id: str,
    window_days: int = 30,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> CustomerTrendsResponse:
    """
    Get sentiment and engagement trends for a customer.

    Returns trend analysis over the specified window (default 30 days),
    including:
    - Sentiment trend direction and summary
    - Engagement trend direction and summary
    - Week-over-week comparisons
    - Daily data for sparkline visualization

    Used by:
    - RightRail component
    - Today Queue cards
    - Customer Detail page
    """
    logger.info(
        "trends_requested",
        workspace_id=workspace_id,
        customer_id=customer_id,
        window_days=window_days,
        user_id=user.uid,
    )

    dc = get_dataconnect_client()

    sentiment_response = None
    engagement_response = None

    # Get sentiment trends
    try:
        sentiment_service = SentimentTrendService(dc=dc, workspace_id=workspace_id)

        trend = await sentiment_service.get_sentiment_trend(customer_id, window_days=window_days)
        comparison = await sentiment_service.compare_periods(customer_id, current_days=7, previous_days=7)

        sentiment_response = SentimentTrendResponse(
            current_state=trend.current_state,
            direction=trend.direction.value,
            confidence=trend.confidence,
            summary=trend.summary,
            negative_count_30d=trend.negative_count,
            positive_count_30d=trend.positive_count,
            daily_scores=trend.daily_scores,
            week_over_week=WeekOverWeekComparison(
                current=comparison.current_negative_count,
                previous=comparison.previous_negative_count,
                delta=comparison.delta_negative,
                percent_change=None,  # Not computed for sentiment
                interpretation=comparison.interpretation,
            ),
        )
    except Exception as e:
        logger.warning(
            "sentiment_trend_failed",
            customer_id=customer_id,
            error=str(e),
        )

    # Get engagement trends
    try:
        engagement_service = EngagementTrendService(dc=dc, workspace_id=workspace_id)

        trend = await engagement_service.get_engagement_trend(customer_id, window_days=window_days)
        comparison = await engagement_service.compare_periods(customer_id, current_days=7, previous_days=7)

        engagement_response = EngagementTrendResponse(
            direction=trend.direction.value,
            confidence=trend.confidence,
            summary=trend.summary,
            total_interactions_30d=trend.total_interactions,
            inbound_count_30d=trend.inbound_count,
            outbound_count_30d=trend.outbound_count,
            days_since_last_interaction=trend.days_since_last_interaction,
            average_weekly_interactions=trend.average_weekly_interactions,
            channel_breakdown=trend.channel_breakdown,
            daily_totals=[d.total for d in trend.daily_data],
            week_over_week=WeekOverWeekComparison(
                current=comparison.current_count,
                previous=comparison.previous_count,
                delta=comparison.delta,
                percent_change=comparison.percent_change,
                interpretation=comparison.interpretation,
            ),
        )
    except Exception as e:
        logger.warning(
            "engagement_trend_failed",
            customer_id=customer_id,
            error=str(e),
        )

    return CustomerTrendsResponse(
        success=True,
        customer_id=customer_id,
        sentiment=sentiment_response,
        engagement=engagement_response,
        message="Trends retrieved successfully" if (sentiment_response or engagement_response) else "No trend data available",
    )


# =============================================================================
# Customer Insights Endpoints (Firestore-backed real-time)
# =============================================================================


class CustomerInsightResponse(BaseModel):
    """Response from customer insight refresh."""
    success: bool
    customer_id: str
    quadrant: Optional[str] = None
    priority: Optional[str] = None
    engagement_score: Optional[float] = None
    sentiment_score: Optional[float] = None
    message: Optional[str] = None


class PortfolioSnapshotResponse(BaseModel):
    """Response with portfolio snapshot data."""
    success: bool
    customer_count: int
    healthy_count: int
    quiet_count: int
    going_dark_count: int
    escalating_count: int
    slipping_count: int
    priority_list: list[dict]
    customers: list[dict]


@router.post("/{workspace_id}/customers/{customer_id}/insights/refresh")
async def refresh_customer_insights(
    workspace_id: str,
    customer_id: str,
    background_tasks: BackgroundTasks,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> CustomerInsightResponse:
    """
    Trigger recomputation of customer insights and cache to Firestore.

    Called by frontend when Firestore cache is empty/stale.
    The insights will be available via Firestore subscription after completion.
    """
    logger.info(
        "customer_insight_refresh_requested",
        workspace_id=workspace_id,
        customer_id=customer_id,
        user_id=user.uid,
    )

    try:
        from services.customer_insights_service import CustomerInsightsService

        dc = get_dataconnect_client()
        service = CustomerInsightsService(dc=dc, workspace_id=workspace_id)

        insight = await service.update_customer_insight(customer_id)

        return CustomerInsightResponse(
            success=True,
            customer_id=customer_id,
            quadrant=insight.quadrant,
            priority=insight.priority,
            engagement_score=insight.engagement_score,
            sentiment_score=insight.sentiment_score,
            message="Insights refreshed successfully",
        )

    except Exception as e:
        logger.error(
            "customer_insight_refresh_failed",
            workspace_id=workspace_id,
            customer_id=customer_id,
            error=str(e),
        )
        return CustomerInsightResponse(
            success=False,
            customer_id=customer_id,
            message=f"Failed to refresh insights: {str(e)}",
        )


@router.get("/{workspace_id}/portfolio/insights")
async def get_portfolio_insights(
    workspace_id: str,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> PortfolioSnapshotResponse:
    """
    Get portfolio-level insights.

    Computes portfolio snapshot on-demand if Firestore is empty.
    Also triggers async write to Firestore for caching.
    """
    logger.info(
        "portfolio_insights_requested",
        workspace_id=workspace_id,
        user_id=user.uid,
    )

    try:
        from services.customer_insights_service import CustomerInsightsService

        dc = get_dataconnect_client()
        service = CustomerInsightsService(dc=dc, workspace_id=workspace_id)

        snapshot = await service.update_portfolio_snapshot()

        return PortfolioSnapshotResponse(
            success=True,
            customer_count=snapshot.customer_count,
            healthy_count=snapshot.healthy_count,
            quiet_count=snapshot.quiet_count,
            going_dark_count=snapshot.going_dark_count,
            escalating_count=snapshot.escalating_count,
            slipping_count=snapshot.slipping_count,
            priority_list=snapshot.priority_list,
            customers=snapshot.customers,
        )

    except Exception as e:
        logger.error(
            "portfolio_insights_failed",
            workspace_id=workspace_id,
            error=str(e),
        )
        return PortfolioSnapshotResponse(
            success=False,
            customer_count=0,
            healthy_count=0,
            quiet_count=0,
            going_dark_count=0,
            escalating_count=0,
            slipping_count=0,
            priority_list=[],
            customers=[],
        )


@router.post("/{workspace_id}/insights/refresh-all")
async def refresh_all_insights(
    workspace_id: str,
    background_tasks: BackgroundTasks,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
):
    """
    Trigger full recomputation of all customer insights.

    Runs as background task to avoid timeout.
    Used by cron or manual refresh.
    """
    logger.info(
        "all_insights_refresh_requested",
        workspace_id=workspace_id,
        user_id=user.uid,
    )

    from services.customer_insights_service import refresh_all_customer_insights

    background_tasks.add_task(
        refresh_all_customer_insights,
        workspace_id=workspace_id,
    )

    return {"status": "queued", "message": "Refresh started in background"}

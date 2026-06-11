"""
Health Scoring Service
Calculates customer relationship health scores based on signals and engagement
"""

from datetime import datetime, timezone, timedelta
from typing import Any
from dataclasses import dataclass

from db.dataconnect_client import DataConnectClient
from core.logging import get_logger

logger = get_logger("HealthScoringService")


@dataclass
class HealthWeights:
    """Configurable weights for health scoring algorithm."""

    # Signal impact weights
    frustrated_signal: int = -20
    positive_signal: int = 10
    neutral_signal: int = 0

    # Time decay weights
    recent_multiplier: float = 2.0  # Signals in last 7 days weighted 2x
    recent_days_threshold: int = 7

    # Stakeholder engagement weights
    active_champion_bonus: int = 15
    departed_champion_penalty: int = -25
    low_engagement_penalty: int = -10

    # Base score
    base_score: int = 50


@dataclass
class HealthScore:
    """Result of health scoring calculation."""

    score: int
    health: str  # strong/healthy/stable/at_risk/deteriorating
    reason: str
    signal_contributions: dict[str, int]
    stakeholder_contribution: int


class HealthScoringService:
    """Service for calculating customer relationship health scores."""

    def __init__(self, dc: DataConnectClient, workspace_id: str, weights: HealthWeights | None = None):
        self.dc = dc
        self.workspace_id = workspace_id
        self.weights = weights or HealthWeights()

    async def calculate_health(
        self,
        customer_id: str,
        updated_by: str = "system:health_scoring",
        trigger: str = "sweep",
    ) -> HealthScore:
        """
        Calculate health score for a customer based on signals and engagement.

        Args:
            customer_id: The customer UUID
            updated_by: Who/what triggered the calculation
            trigger: MetricSnapshot trigger label for the append-on-change row
                     (e.g. "scheduled_daily", "risk_signal"). Defaults to "sweep".

        Returns:
            HealthScore with score, health status, and reasoning
        """
        # Fetch active signals for the customer
        signals_result = await self.dc.execute_query(
            "GetCustomerSignals",
            {"customerId": customer_id}
        )

        # Firebase SQL Connect returns results directly without a "data" wrapper
        signals = signals_result.get("customer", {}).get("signals_on_customer", [])

        # Fetch stakeholders for engagement assessment
        stakeholders_result = await self.dc.execute_query(
            "GetCustomerStakeholders",
            {"customerId": customer_id}
        )

        stakeholders = stakeholders_result.get("customer", {}).get("stakeholders_on_customer", [])

        # Read the prior snapshot before overwriting the current value, so the
        # append-on-change row can record where the score moved FROM (no-op when
        # the metric-snapshots flag is off — get_latest returns None).
        from services import metric_snapshots

        prior_snapshot = await metric_snapshots.get_latest(
            self.workspace_id, customer_id, "health_score"
        )
        prev_score: float | None = (
            float(prior_snapshot["value"])
            if prior_snapshot and prior_snapshot.get("value") is not None
            else None
        )

        # Calculate score
        score_data = self._calculate_score(signals, stakeholders)

        # Determine health status from score
        health_status = self._score_to_health(score_data.score)

        # Enrich reason with sentiment trend context
        enriched_reason = await self._enrich_reason_with_trend(
            customer_id,
            score_data.reason,
        )

        # Update customer record
        await self._update_customer_health(
            customer_id,
            health_status,
            score_data.score,
            enriched_reason,
            updated_by,
        )

        # Append-on-change: record the new value, where it came from, and the
        # contributing factors (best-effort; never raises, no-op when flag off).
        await metric_snapshots.append_snapshot(
            workspace_id=self.workspace_id,
            customer_id=customer_id,
            metric="health_score",
            value=float(score_data.score),
            prev_value=prev_score,
            trigger=trigger,
            inputs={
                "health_status": health_status,
                "signal_contributions": score_data.signal_contributions,
                "stakeholder_contribution": score_data.stakeholder_contribution,
                "reason": enriched_reason,
                "updated_by": updated_by,
            },
        )

        logger.info(
            "health_score_calculated",
            customer_id=customer_id,
            score=score_data.score,
            health=health_status,
            signal_count=len(signals),
            stakeholder_count=len(stakeholders),
        )

        return HealthScore(
            score=score_data.score,
            health=health_status,
            reason=score_data.reason,
            signal_contributions=score_data.signal_contributions,
            stakeholder_contribution=score_data.stakeholder_contribution,
        )

    def _calculate_score(
        self,
        signals: list[dict[str, Any]],
        stakeholders: list[dict[str, Any]],
    ) -> HealthScore:
        """
        Internal method to calculate health score.

        Algorithm:
        1. Start at base score (50)
        2. Add/subtract points for each signal based on (kind, state)
        3. Apply 2x weight to recent signals (last 7 days)
        4. Factor in stakeholder engagement

        Signal Schema (from schema.gql):
        - kind: engagement | sentiment | commitments
        - state: ok | warn | risk

        Impact Mapping:
        - (sentiment, risk) → frustrated (-20)
        - (sentiment, ok) → positive (+10)
        - (engagement, risk) → going dark (-15)
        - (engagement, ok) → engaged (+5)
        - (commitments, risk) → overdue commitment (-10)
        - All others → neutral (0)
        """
        score = self.weights.base_score
        signal_contributions = {}
        reason_parts = []

        # Get current time for recency calculation
        now = datetime.now(timezone.utc)
        recent_threshold = now - timedelta(days=self.weights.recent_days_threshold)

        # Process signals - track by impact type
        negative_count = 0
        positive_count = 0
        recent_negative = 0
        recent_positive = 0

        for signal in signals:
            # Skip superseded signals (inactive)
            # Note: "state" in schema is ok/warn/risk, NOT active/inactive
            # Active signals are those without supersededAt
            if signal.get("supersededAt"):
                continue

            kind = signal.get("kind", "")
            state = signal.get("state", "")
            generated_at_str = signal.get("generatedAt")

            # Parse timestamp
            try:
                generated_at = datetime.fromisoformat(generated_at_str.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                generated_at = now  # Default to now if parsing fails

            is_recent = generated_at >= recent_threshold

            # Determine signal impact based on (kind, state) combination
            impact = self._get_signal_impact(kind, state)
            impact_type = "neutral"

            if impact < 0:
                negative_count += 1
                impact_type = "negative"
                if is_recent:
                    recent_negative += 1
                    impact = int(impact * self.weights.recent_multiplier)
            elif impact > 0:
                positive_count += 1
                impact_type = "positive"
                if is_recent:
                    recent_positive += 1
                    impact = int(impact * self.weights.recent_multiplier)

            score += impact

            # Track contributions by kind+state for transparency
            contrib_key = f"{kind}:{state}"
            signal_contributions[contrib_key] = signal_contributions.get(contrib_key, 0) + impact

        # Build signal reasoning
        if recent_negative > 0:
            reason_parts.append(f"{recent_negative} recent negative signal(s)")
        if recent_positive > 0:
            reason_parts.append(f"{recent_positive} recent positive signal(s)")
        if negative_count > recent_negative:
            reason_parts.append(f"{negative_count - recent_negative} older negative signal(s)")
        if positive_count > recent_positive:
            reason_parts.append(f"{positive_count - recent_positive} older positive signal(s)")

        # Assess stakeholder engagement
        stakeholder_contribution = self._assess_stakeholder_engagement(stakeholders, reason_parts)
        score += stakeholder_contribution

        # Clamp score to 0-100 range
        score = max(0, min(100, int(score)))

        # Build reason string
        if not reason_parts:
            reason = "No significant signals or engagement factors"
        else:
            reason = "; ".join(reason_parts)

        return HealthScore(
            score=score,
            health="",  # Will be set by _score_to_health
            reason=reason,
            signal_contributions=signal_contributions,
            stakeholder_contribution=stakeholder_contribution,
        )

    def _get_signal_impact(self, kind: str, state: str) -> int:
        """
        Determine health score impact from signal (kind, state) combination.

        Uses the actual schema values:
        - kind: engagement | sentiment | commitments
        - state: ok | warn | risk

        Returns:
            Integer impact on health score (negative = bad, positive = good)
        """
        # Sentiment signals have the biggest impact on perceived health
        if kind == "sentiment":
            if state == "risk":
                # Frustrated customer - significant negative impact
                return self.weights.frustrated_signal  # -20
            elif state == "ok":
                # Happy customer - positive impact
                return self.weights.positive_signal  # +10
            else:  # warn
                # Concerns raised - minor negative impact
                return -5

        # Engagement signals indicate activity patterns
        elif kind == "engagement":
            if state == "risk":
                # Going dark - negative impact
                return self.weights.low_engagement_penalty  # -10
            elif state == "ok":
                # Active engagement - modest positive impact
                return 5
            else:  # warn
                # Declining engagement - minor negative
                return -3

        # Commitment signals track promises/deadlines
        elif kind == "commitments":
            if state == "risk":
                # Overdue commitments - negative impact
                return -10
            elif state == "ok":
                # Commitments kept - small positive
                return 3
            else:  # warn
                # Approaching deadlines - neutral to minor negative
                return -2

        # Unknown signal types are neutral
        return self.weights.neutral_signal

    def _assess_stakeholder_engagement(
        self,
        stakeholders: list[dict[str, Any]],
        reason_parts: list[str],
    ) -> int:
        """
        Assess stakeholder engagement and return score contribution.

        Factors:
        - Active champion: +15
        - Departed champion: -25
        - Low engagement (no interactions in 30+ days): -10
        """
        contribution = 0

        active_champions = 0
        departed_champions = 0
        low_engagement_count = 0

        now = datetime.now(timezone.utc)
        engagement_threshold = now - timedelta(days=30)

        for stakeholder in stakeholders:
            status = stakeholder.get("status", "")
            role = stakeholder.get("role", "").lower()
            last_interaction_str = stakeholder.get("lastInteractionAt")

            # Check if champion
            is_champion = "champion" in role or "decision" in role or "buyer" in role

            if status == "departed" and is_champion:
                departed_champions += 1
                contribution += self.weights.departed_champion_penalty
            elif status == "active":
                if is_champion:
                    active_champions += 1
                    contribution += self.weights.active_champion_bonus

                # Check engagement level
                if last_interaction_str:
                    try:
                        last_interaction = datetime.fromisoformat(last_interaction_str.replace('Z', '+00:00'))
                        if last_interaction < engagement_threshold:
                            low_engagement_count += 1
                            contribution += self.weights.low_engagement_penalty
                    except (ValueError, AttributeError):
                        pass

        # Add to reasoning
        if active_champions > 0:
            reason_parts.append(f"{active_champions} active champion(s)")
        if departed_champions > 0:
            reason_parts.append(f"{departed_champions} departed champion(s)")
        if low_engagement_count > 0:
            reason_parts.append(f"{low_engagement_count} low-engagement stakeholder(s)")

        return contribution

    def _score_to_health(self, score: int) -> str:
        """
        Convert numeric score to health status enum.

        Thresholds:
        - 80+: strong
        - 60-79: healthy
        - 40-59: stable
        - 20-39: at_risk
        - 0-19: deteriorating
        """
        if score >= 80:
            return "strong"
        elif score >= 60:
            return "healthy"
        elif score >= 40:
            return "stable"
        elif score >= 20:
            return "at_risk"
        else:
            return "deteriorating"

    async def _enrich_reason_with_trend(
        self,
        customer_id: str,
        base_reason: str,
    ) -> str:
        """
        Enrich health reason with sentiment trend context.

        Adds trend information (improving/declining) when significant
        sentiment patterns are detected.

        Args:
            customer_id: Customer UUID string
            base_reason: The base reason from signal/stakeholder analysis

        Returns:
            Enriched reason string with trend context
        """
        try:
            from services.sentiment_trend_service import SentimentTrendService, TrendDirection

            trend_service = SentimentTrendService(dc=self.dc, workspace_id=self.workspace_id)
            comparison = await trend_service.compare_periods(
                customer_id,
                current_days=7,
                previous_days=7,
            )

            # Only add trend context if there's a meaningful change
            if abs(comparison.delta_negative) >= 1 or abs(comparison.delta_positive) >= 2:
                trend_context = f"Trend: {comparison.interpretation}"
                if base_reason:
                    return f"{base_reason}. {trend_context}"
                return trend_context

            return base_reason

        except Exception as e:
            # Don't fail health scoring if trend analysis fails
            logger.debug(
                "trend_enrichment_failed",
                customer_id=customer_id,
                error=str(e),
            )
            return base_reason

    async def _update_customer_health(
        self,
        customer_id: str,
        health: str,
        score: int,
        reason: str,
        updated_by: str,
    ) -> None:
        """Update customer health fields in the database."""
        try:
            await self.dc.execute_mutation(
                "UpdateCustomerHealth",
                {
                    "customerId": customer_id,
                    "relationshipHealth": health,
                    "relationshipHealthScore": score,
                    "relationshipHealthReason": reason,
                    "relationshipHealthUpdatedBy": updated_by,
                }
            )

            logger.info(
                "customer_health_updated",
                customer_id=customer_id,
                health=health,
                score=score,
                updated_by=updated_by,
            )
        except Exception as e:
            logger.error(
                "failed_to_update_customer_health",
                customer_id=customer_id,
                error=str(e),
            )
            raise

    async def recalculate_all_customers(self) -> dict[str, Any]:
        """
        Recalculate health scores for all customers in the workspace.

        Returns:
            Summary with counts and results
        """
        # Fetch all customers in workspace
        customers_result = await self.dc.execute_query(
            "GetWorkspaceCustomers",
            {"workspaceId": self.workspace_id}
        )

        # Firebase SQL Connect returns results directly without a "data" wrapper
        customers = customers_result.get("customers", [])

        results = {
            "total": len(customers),
            "updated": 0,
            "failed": 0,
            "errors": [],
        }

        for customer in customers:
            customer_id = customer.get("id")
            try:
                await self.calculate_health(customer_id, updated_by="system:bulk_recalculation")
                results["updated"] += 1
            except Exception as e:
                results["failed"] += 1
                results["errors"].append({
                    "customer_id": customer_id,
                    "error": str(e),
                })
                logger.error(
                    "health_calculation_failed",
                    customer_id=customer_id,
                    error=str(e),
                )

        logger.info(
            "bulk_health_recalculation_complete",
            workspace_id=self.workspace_id,
            total=results["total"],
            updated=results["updated"],
            failed=results["failed"],
        )

        return results

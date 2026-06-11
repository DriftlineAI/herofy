"""
Signal Sweep Service

Background sweep detectors for absence- and trend-based signals that have
no inbound event to trigger them. Runs on a scheduler (nightly or hourly).

Detectors:
  GoingDarkDetector      — customer has gone silent past a lifecycle threshold
  EngagementTrendDetector — inbound interaction volume dropped ≥50% over 14 days
  SentimentTrendDetector  — sentiment signals trending negative over 30 days

Each detector:
  1. Queries DB deterministically (no LLM)
  2. Checks for an existing active Signal of the same kind before writing
  3. Checks for an existing open Need of the same type before writing
  4. Emits a SweepFinding if the condition is genuinely new
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from db.dataconnect_client import get_dataconnect_client
from core.logging import get_logger
# Lifecycle days-silent thresholds live in engagement_health_service as the single
# source of truth (the derived score uses the same baseline). Aliased to preserve
# the local name used throughout GoingDarkDetector.
from services.engagement_health_service import LIFECYCLE_THRESHOLDS as _GOING_DARK_THRESHOLDS

logger = get_logger("SignalSweepService")

# Placeholder handbook version used for sweep-generated signals (no handbook context)
_HANDBOOK_PLACEHOLDER = "00000000-0000-0000-0000-000000000000"

_GOING_DARK_RISK_MULTIPLIER = 2  # state escalates to risk at 2× the threshold

# Engagement trend window in days (compare last N days vs prior N days)
_TREND_WINDOW_DAYS = 14
_TREND_WARN_RATIO = 0.5   # <50% of prior volume → warn
_TREND_RISK_RATIO = 0.25  # <25% of prior volume → risk
_TREND_MIN_PRIOR = 2      # skip if prior window had fewer than 2 interactions (not meaningful)

# Sentiment trend: minimum signals needed to compute a trend
_SENTIMENT_MIN_SIGNALS = 3


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SweepFinding:
    customer_id: str
    customer_name: str
    signal_kind: str       # 'going_dark' | 'engagement' | 'cadence' | 'sentiment'
    signal_state: str      # 'warn' | 'risk'
    need_type: str         # maps to NeedType enum
    sentence: str          # one-line human-readable description
    evidence_text: str     # supporting detail
    next_action: str       # suggested CSM action
    inputs_hash: str       # deterministic hash for dedup


@dataclass
class SweepSummary:
    workspace_id: str
    customers_checked: int = 0
    findings: list[SweepFinding] = field(default_factory=list)
    signals_created: int = 0
    skipped_dedup: int = 0
    errors: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _inputs_hash(*parts: str) -> str:
    """Deterministic SHA256 hash of sweep inputs (for Signal.inputsHash)."""
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _ts(dt: datetime) -> str:
    """ISO timestamp string for DataConnect."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def decide_engagement_finding(
    health_state: str,
    dark_state: str | None,
    cadence_state: str | None,
    existing_engagement_state: str | None,
) -> str | None:
    """Pure decision for EngagementHealthDetector: should the derived detector emit a
    finding, and at what state? Returns the state to fire, or None to skip.

    Rules (additive, anti-double-fire):
      - "ok" derived state → never fires.
      - skip a derived "warn" when BOTH flat detectors (going_dark + cadence) are
        already at risk (pure pile-on; the router already escalated the task).
      - own-kind dedup: skip when an equal-or-higher active "engagement" signal exists
        (allows warn → risk escalation through).
    """
    if health_state == "ok":
        return None
    if dark_state == "risk" and cadence_state == "risk" and health_state == "warn":
        return None
    if existing_engagement_state == "risk" or existing_engagement_state == health_state:
        return None
    return health_state


def _score_to_state(score: float) -> str:
    """Map a 0-1 score to a state string for the raw engagement/sentiment snapshots.

    These are CustomerInsight scores (a different distribution than the derived
    composite), so the breakpoints here are intentionally NOT the same as the
    lifecycle-tuned thresholds in EngagementHealthResult.state — this only labels
    the descriptive engagement/sentiment heartbeat rows, it does not drive detection.
    """
    if score >= 0.65:
        return "ok"
    if score >= 0.40:
        return "warn"
    return "risk"


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

class GoingDarkDetector:
    """
    Detects customers who have gone silent past their lifecycle threshold.
    Uses Customer.lastInteractionAt (inbound direction only, maintained by DB trigger).
    """

    async def detect(
        self,
        workspace_id: str,
        customers: list[dict[str, Any]],
        dc,
        ctx: dict | None = None,
    ) -> list[SweepFinding]:
        now = datetime.now(timezone.utc)
        findings: list[SweepFinding] = []

        for customer in customers:
            customer_id = str(customer["id"])
            lifecycle = customer.get("lifecycle", "active")
            threshold_days = _GOING_DARK_THRESHOLDS.get(lifecycle, 7)

            last_interaction = await dc.execute_query(
                "GetLastInboundInteraction",
                {"workspaceId": workspace_id, "customerId": customer_id},
            )
            interactions = last_interaction.get("interactions", [])
            last_at = _parse_ts(interactions[0]["occurredAt"]) if interactions else None

            if last_at is None:
                # No inbound interaction ever recorded — treat as long silent
                last_at = datetime.now(timezone.utc) - timedelta(days=threshold_days * 3)

            days_silent = (now - last_at).days
            if days_silent < threshold_days:
                continue

            # Check: existing active going_dark signal already exists → skip,
            # UNLESS this run would escalate from warn → risk.
            existing = await dc.execute_query(
                "GetActiveSignalByKind",
                {
                    "workspaceId": workspace_id,
                    "customerId": customer_id,
                    "kind": "going_dark",
                },
            )
            if existing.get("signals"):
                existing_state = existing["signals"][0].get("state")
                new_state = "risk" if days_silent >= threshold_days * _GOING_DARK_RISK_MULTIPLIER else "warn"
                if existing_state == "risk" or existing_state == new_state:
                    logger.debug(
                        "going_dark_skipped_active_signal",
                        customer_id=customer_id,
                        days_silent=days_silent,
                    )
                    continue
                # warn → risk escalation: fall through to emit the new finding

            # Check: existing open going_dark Need → skip
            existing_need = await dc.execute_query(
                "FindOpenNeedByType",
                {
                    "workspaceId": workspace_id,
                    "customerId": customer_id,
                    "needType": "going_dark",
                },
            )
            if existing_need.get("needs"):
                logger.debug(
                    "going_dark_skipped_open_need",
                    customer_id=customer_id,
                    days_silent=days_silent,
                )
                continue

            state = "risk" if days_silent >= threshold_days * _GOING_DARK_RISK_MULTIPLIER else "warn"
            sentence = (
                f"No inbound contact from {customer['name']} for {days_silent} days"
            )
            evidence = (
                f"Last inbound interaction: {last_at.strftime('%Y-%m-%d')}. "
                f"Lifecycle: {lifecycle}. Threshold: {threshold_days}d."
            )
            next_action = f"Reach out to check in with {customer['name']}"

            findings.append(SweepFinding(
                customer_id=customer_id,
                customer_name=customer["name"],
                signal_kind="going_dark",
                signal_state=state,
                need_type="going_dark",
                sentence=sentence,
                evidence_text=evidence,
                next_action=next_action,
                inputs_hash=_inputs_hash(
                    customer_id, "going_dark", str(days_silent // threshold_days)
                ),
            ))

        return findings


class EngagementTrendDetector:
    """
    Detects significant drops in inbound interaction volume.
    Compares the last 14 days against the prior 14 days.
    """

    async def detect(
        self,
        workspace_id: str,
        customers: list[dict[str, Any]],
        dc,
        ctx: dict | None = None,
    ) -> list[SweepFinding]:
        now = datetime.now(timezone.utc)
        window_end = now
        window_mid = now - timedelta(days=_TREND_WINDOW_DAYS)
        window_start = now - timedelta(days=_TREND_WINDOW_DAYS * 2)

        findings: list[SweepFinding] = []

        for customer in customers:
            customer_id = str(customer["id"])

            # Fetch both windows in parallel
            prior_result, recent_result = await _fetch_two_windows(
                dc, workspace_id, customer_id, window_start, window_mid, window_end
            )

            prior_count = len(prior_result.get("interactions", []))
            recent_count = len(recent_result.get("interactions", []))

            if prior_count < _TREND_MIN_PRIOR:
                continue  # not enough history to establish a trend

            if recent_count == 0:
                ratio = 0.0
            else:
                ratio = recent_count / prior_count

            if ratio >= _TREND_WARN_RATIO:
                continue  # no meaningful drop

            # Check existing active cadence signal; allow warn → risk escalation.
            existing = await dc.execute_query(
                "GetActiveSignalByKind",
                {
                    "workspaceId": workspace_id,
                    "customerId": customer_id,
                    "kind": "cadence",
                },
            )
            if existing.get("signals"):
                existing_state = existing["signals"][0].get("state")
                new_state = "risk" if ratio < _TREND_RISK_RATIO else "warn"
                if existing_state == "risk" or existing_state == new_state:
                    continue
                # warn → risk escalation: fall through

            state = "risk" if ratio < _TREND_RISK_RATIO else "warn"
            pct_drop = int((1 - ratio) * 100)
            sentence = (
                f"{customer['name']} inbound contact dropped {pct_drop}% "
                f"({recent_count} vs {prior_count} in prior 2 weeks)"
            )
            evidence = (
                f"Prior 14d: {prior_count} inbound interactions. "
                f"Last 14d: {recent_count}. "
                f"Drop ratio: {pct_drop}%."
            )
            next_action = "Review recent threads and consider proactive outreach"

            findings.append(SweepFinding(
                customer_id=customer_id,
                customer_name=customer["name"],
                signal_kind="cadence",
                signal_state=state,
                need_type="going_dark",  # routes to same Need type as absence
                sentence=sentence,
                evidence_text=evidence,
                next_action=next_action,
                inputs_hash=_inputs_hash(
                    customer_id, "cadence", str(prior_count), str(recent_count)
                ),
            ))

        return findings


class SentimentTrendDetector:
    """
    Detects negative sentiment drift by comparing the state distribution
    of recent sentiment signals against earlier ones in the past 30 days.
    Requires at least 3 signals to compute a meaningful trend.
    """

    async def detect(
        self,
        workspace_id: str,
        customers: list[dict[str, Any]],
        dc,
        ctx: dict | None = None,
    ) -> list[SweepFinding]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        findings: list[SweepFinding] = []

        for customer in customers:
            customer_id = str(customer["id"])

            result = await dc.execute_query(
                "GetRecentSentimentSignals",
                {
                    "workspaceId": workspace_id,
                    "customerId": customer_id,
                    "after": _ts(cutoff),
                },
            )
            signals = result.get("signals", [])

            if len(signals) < _SENTIMENT_MIN_SIGNALS:
                continue

            # Split into earlier half and later half (already ordered ASC by generatedAt)
            mid = len(signals) // 2
            earlier = signals[:mid]
            later = signals[mid:]

            def negative_ratio(items: list[dict]) -> float:
                neg = sum(1 for s in items if s.get("state") in ("warn", "risk"))
                return neg / len(items) if items else 0.0

            earlier_neg = negative_ratio(earlier)
            later_neg = negative_ratio(later)

            # Only flag if later half is materially more negative than earlier
            if later_neg - earlier_neg < 0.3:
                continue

            # Check existing active sentiment signal
            existing = await dc.execute_query(
                "GetActiveSignalByKind",
                {
                    "workspaceId": workspace_id,
                    "customerId": customer_id,
                    "kind": "sentiment",
                },
            )
            if existing.get("signals"):
                existing_state = existing["signals"][0].get("state")
                # Only skip if it's already risk — a warn → risk escalation should still fire
                if existing_state == "risk":
                    continue

            state = "risk" if later_neg >= 0.75 else "warn"
            sentence = (
                f"{customer['name']} sentiment trending negative "
                f"({int(later_neg * 100)}% negative signals in last 15 days)"
            )
            evidence = (
                f"Last 30d: {len(signals)} sentiment signals. "
                f"Earlier half: {int(earlier_neg * 100)}% negative. "
                f"Later half: {int(later_neg * 100)}% negative."
            )
            next_action = "Review recent interactions and address sources of friction"

            findings.append(SweepFinding(
                customer_id=customer_id,
                customer_name=customer["name"],
                signal_kind="sentiment",
                signal_state=state,
                need_type="frustrated_signal",
                sentence=sentence,
                evidence_text=evidence,
                next_action=next_action,
                inputs_hash=_inputs_hash(
                    customer_id, "sentiment_trend",
                    str(int(earlier_neg * 100)), str(int(later_neg * 100))
                ),
            ))

        return findings


class EngagementHealthDetector:
    """
    Derived engagement-health detector (additive — sits beside the flat
    GoingDarkDetector, which stays as the reliable backbone).

    Consumes the precomputed EngagementHealthResult that the heartbeat already
    built for each customer (passed via `ctx`); it never recomputes. It emits a
    signal_kind="engagement" finding — a valid SignalKind that no flat detector
    uses and that the signal router already routes — when the DERIVED composite
    score indicates risk the flat thresholds miss (the "cadence + sentiment
    slipping but not yet fully silent" case).

    Anti-double-fire: if BOTH flat detectors (going_dark + cadence) have already
    fired at risk for this customer, a derived 'warn' adds no decision value, so
    it is skipped — the router already escalated the queued task. Returns [] when
    the metric-snapshots flag is off / ctx is empty (heartbeat didn't run).
    """

    async def detect(
        self,
        workspace_id: str,
        customers: list[dict[str, Any]],
        dc,
        ctx: dict | None = None,
    ) -> list[SweepFinding]:
        if not ctx:
            return []

        findings: list[SweepFinding] = []
        for customer in customers:
            customer_id = str(customer["id"])
            health = ctx.get(customer_id)
            if not health or health.state == "ok":
                continue
            lifecycle = customer.get("lifecycle", "active")

            try:
                # Gather the existing flat (going_dark/cadence) + own (engagement) signal
                # states, then let the pure decision decide whether to fire.
                dark = await dc.execute_query(
                    "GetActiveSignalByKind",
                    {"workspaceId": workspace_id, "customerId": customer_id, "kind": "going_dark"},
                )
                cadence = await dc.execute_query(
                    "GetActiveSignalByKind",
                    {"workspaceId": workspace_id, "customerId": customer_id, "kind": "cadence"},
                )
                existing = await dc.execute_query(
                    "GetActiveSignalByKind",
                    {"workspaceId": workspace_id, "customerId": customer_id, "kind": "engagement"},
                )
                dark_state = dark["signals"][0]["state"] if dark.get("signals") else None
                cadence_state = cadence["signals"][0]["state"] if cadence.get("signals") else None
                existing_state = existing["signals"][0]["state"] if existing.get("signals") else None

                fire_state = decide_engagement_finding(
                    health.state, dark_state, cadence_state, existing_state
                )
                if fire_state is None:
                    logger.debug(
                        "engagement_health_skipped",
                        customer_id=customer_id,
                        score=health.score,
                        health_state=health.state,
                    )
                    continue

                sentence = (
                    f"{customer['name']} engagement health {health.state}: {health.explanation}"
                )
                evidence = (
                    f"Derived score {health.score:.2f} "
                    f"(recency {health.components['recency']:.2f}, "
                    f"cadence {health.components['cadence']:.2f}, "
                    f"sentiment {health.components['sentiment']:.2f}); "
                    f"lifecycle {lifecycle}, confidence {health.confidence}."
                )
                next_action = (
                    "Review engagement pattern — trend suggests relationship risk "
                    "not captured by absence alone"
                )

                findings.append(SweepFinding(
                    customer_id=customer_id,
                    customer_name=customer["name"],
                    signal_kind="engagement",
                    signal_state=health.state,
                    need_type="going_dark",  # routes to the same Need bucket as absence
                    sentence=sentence,
                    evidence_text=evidence,
                    next_action=next_action,
                    inputs_hash=_inputs_hash(
                        customer_id, "engagement_health",
                        str(int(health.score * 100)), health.state, lifecycle,
                    ),
                ))

            except Exception as e:
                logger.error(
                    "engagement_health_detector_failed",
                    customer_id=customer_id,
                    error=str(e),
                )

        return findings


# ---------------------------------------------------------------------------
# Parallel window helper (avoids sequential awaits per customer)
# ---------------------------------------------------------------------------

async def _fetch_two_windows(dc, workspace_id, customer_id, start, mid, end):
    import asyncio
    prior, recent = await asyncio.gather(
        dc.execute_query(
            "GetInteractionsInWindow",
            {
                "workspaceId": workspace_id,
                "customerId": customer_id,
                "after": _ts(start),
                "before": _ts(mid),
            },
        ),
        dc.execute_query(
            "GetInteractionsInWindow",
            {
                "workspaceId": workspace_id,
                "customerId": customer_id,
                "after": _ts(mid),
                "before": _ts(end),
            },
        ),
    )
    return prior, recent


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------

class SignalSweepService:
    """
    Orchestrates all sweep detectors for a workspace.
    Persists SweepFindings as Signal rows (dedup-guarded).
    """

    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id
        self.dc = get_dataconnect_client()
        self._detectors = [
            GoingDarkDetector(),
            EngagementTrendDetector(),
            SentimentTrendDetector(),
            EngagementHealthDetector(),  # consumes the heartbeat ctx; no-op when flag off
        ]

    async def run(self) -> SweepSummary:
        # No request user on the cron detector path — impersonate the workspace owner so the
        # detectors' @check(auth.uid) reads pass on the admin surface. (Harmless when a request
        # already set impersonation: same membership boundary, reverted on exit.)
        async with self.dc.impersonate_workspace_owner(self.workspace_id):
            return await self._run()

    async def _run(self) -> SweepSummary:
        summary = SweepSummary(workspace_id=self.workspace_id)

        customers = await self._get_customers()
        summary.customers_checked = len(customers)

        if not customers:
            logger.info("sweep_no_customers", workspace_id=self.workspace_id)
            return summary

        # Daily heartbeat (flag-gated): append per-metric snapshots for each
        # customer and precompute the derived engagement-health result that the
        # EngagementHealthDetector consumes below. No-op when the flag is off.
        ctx: dict[str, Any] = {}
        from config import get_settings
        if get_settings().metric_snapshots_enabled:
            try:
                ctx = await self._run_heartbeat(customers)
            except Exception as e:
                summary.errors += 1
                logger.error(
                    "sweep_heartbeat_failed",
                    workspace_id=self.workspace_id,
                    error=str(e),
                )

        for detector in self._detectors:
            try:
                findings = await detector.detect(
                    self.workspace_id, customers, self.dc, ctx=ctx
                )
                summary.findings.extend(findings)
            except Exception as e:
                summary.errors += 1
                logger.error(
                    "sweep_detector_failed",
                    detector=type(detector).__name__,
                    workspace_id=self.workspace_id,
                    error=str(e),
                )

        for finding in summary.findings:
            try:
                created = await self._persist_finding(finding)
                if created:
                    summary.signals_created += 1
                else:
                    summary.skipped_dedup += 1
            except Exception as e:
                summary.errors += 1
                logger.error(
                    "sweep_persist_failed",
                    customer_id=finding.customer_id,
                    kind=finding.signal_kind,
                    error=str(e),
                )

        logger.info(
            "sweep_complete",
            workspace_id=self.workspace_id,
            customers_checked=summary.customers_checked,
            signals_created=summary.signals_created,
            skipped_dedup=summary.skipped_dedup,
            errors=summary.errors,
        )
        return summary

    async def _get_customers(self) -> list[dict[str, Any]]:
        result = await self.dc.execute_query(
            "GetCustomersForSweep", {"workspaceId": self.workspace_id}
        )
        return result.get("customers", [])

    async def _run_heartbeat(self, customers: list[dict[str, Any]]) -> dict[str, Any]:
        """Daily heartbeat: per customer, refresh the cached insight and append a
        snapshot per account-level metric (engagement, sentiment, engagement_health)
        even when nothing changed — so sparklines/baselines get an evenly-spaced
        sample. Returns {customer_id: EngagementHealthResult} for the detector to
        reuse (computed once here, never recomputed).

        Recompute path (vs reading the cached insight) is deliberate: the heartbeat's
        purpose is a CURRENT sample, and update_customer_insight() also refreshes the
        Firestore UI cache as a side benefit. Per-customer errors are isolated.
        """
        from services.customer_insights_service import CustomerInsightsService
        from services.engagement_health_service import compute_engagement_health
        from services import metric_snapshots

        insights_service = CustomerInsightsService(dc=self.dc, workspace_id=self.workspace_id)
        ctx: dict[str, Any] = {}

        for customer in customers:
            customer_id = str(customer["id"])
            lifecycle = customer.get("lifecycle", "active")
            try:
                insight = await insights_service.update_customer_insight(
                    customer_id=customer_id,
                    update_portfolio=False,  # batch the portfolio refresh at the end
                )

                await metric_snapshots.append_snapshot(
                    workspace_id=self.workspace_id,
                    customer_id=customer_id,
                    metric="engagement",
                    value=insight.engagement_score,
                    state=_score_to_state(insight.engagement_score),
                    trigger="scheduled_daily",
                    inputs={
                        "days_since_last": insight.days_since_last_interaction,
                        "total_interactions_30d": insight.total_interactions_30d,
                        "direction": insight.engagement_direction,
                    },
                )
                await metric_snapshots.append_snapshot(
                    workspace_id=self.workspace_id,
                    customer_id=customer_id,
                    metric="sentiment",
                    value=insight.sentiment_score,
                    state=_score_to_state(insight.sentiment_score),
                    trigger="scheduled_daily",
                    inputs={
                        "negative_30d": insight.negative_signals_30d,
                        "positive_30d": insight.positive_signals_30d,
                        "direction": insight.sentiment_direction,
                    },
                )

                # Cadence ratio from the insight's week-over-week inbound counts
                # (this account's own baseline). None when there's no prior volume.
                cadence_ratio = (
                    insight.engagement_wow_current / insight.engagement_wow_previous
                    if insight.engagement_wow_previous
                    else None
                )

                # Contact-level overlay (champion silence, responsiveness decay,
                # breadth). None when no stakeholder data → pure account-level scoring.
                from services.responsiveness import gather_contact_signals

                contact = await gather_contact_signals(
                    self.workspace_id, customer_id, lifecycle
                )

                health = compute_engagement_health(
                    lifecycle=lifecycle,
                    days_since_last=insight.days_since_last_interaction,
                    cadence_ratio=cadence_ratio,
                    sentiment_score=insight.sentiment_score,
                    sentiment_direction=insight.sentiment_direction,
                    contact=contact,
                )

                prior = await metric_snapshots.get_latest(
                    self.workspace_id, customer_id, "engagement_health"
                )
                prev_value = prior.get("value") if prior else None
                await metric_snapshots.append_snapshot(
                    workspace_id=self.workspace_id,
                    customer_id=customer_id,
                    metric="engagement_health",
                    value=health.score,
                    state=health.state,
                    prev_value=prev_value,
                    trigger="scheduled_daily",
                    inputs=health.inputs,
                )

                # Commitment follow-through reliability (both sides) — trust + disengagement.
                await self._snapshot_commitment_reliability(customer_id)
                # Milestone velocity + stakeholder-graph health (deterministic metrics).
                await self._snapshot_velocity_metrics(customer_id)
                # Surface the durable engagement-health series to the RightRail via the
                # Firestore hot-cache (sourced from MetricSnapshot, not on-demand recompute).
                await self._cache_engagement_health(customer_id, health)

                ctx[customer_id] = health

            except Exception as e:
                logger.error(
                    "heartbeat_customer_failed",
                    customer_id=customer_id,
                    error=str(e),
                )

        # One portfolio refresh after all per-customer insight updates.
        try:
            await insights_service.update_portfolio_snapshot()
        except Exception as e:
            logger.warning("heartbeat_portfolio_refresh_failed", error=str(e))

        return ctx

    async def _snapshot_commitment_reliability(self, customer_id: str) -> None:
        """Compute and snapshot follow-through reliability for both sides (best-effort).
        Only commitments with a real dueDate are evaluable; sides with nothing to
        evaluate are skipped (no misleading snapshot)."""
        from datetime import date
        from services.commitment_reliability import compute_reliability
        from services import metric_snapshots

        try:
            result = await self.dc.execute_query(
                "GetCustomerCommitmentsForReliability",
                {"workspaceId": self.workspace_id, "customerId": customer_id},
            )
            commitments = result.get("commitments", []) or []
        except Exception as e:
            logger.warning("commitment_reliability_fetch_failed", customer_id=customer_id, error=str(e))
            return

        today = date.today()
        for side, metric in (("us", "commitment_reliability_us"), ("them", "commitment_reliability_them")):
            rel = compute_reliability(commitments, side, today)
            if rel.reliability is None:
                continue  # nothing evaluable for this side yet
            await metric_snapshots.append_snapshot(
                workspace_id=self.workspace_id,
                customer_id=customer_id,
                metric=metric,
                value=rel.reliability,
                trigger="scheduled_daily",
                inputs={"side": side, "evaluated": rel.evaluated, "on_time": rel.on_time, "detail": rel.detail},
            )

    async def _cache_engagement_health(self, customer_id: str, health) -> None:
        """Merge the durable engagement-health series into the Firestore customer_insights
        doc (the RightRail hot-cache). Sourced from MetricSnapshot, so it's recorded
        history, not a sliding-window recompute. Best-effort; never raises."""
        from datetime import datetime, timedelta, timezone
        from services import metric_snapshots
        from services.firestore_service import get_firestore_service, _normalize_uuid

        try:
            since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            snaps = await metric_snapshots.get_recent(
                self.workspace_id, customer_id, "engagement_health", since
            )
            sparkline = [round(s["value"], 3) for s in snaps if s.get("value") is not None]

            direction = "stable"
            if len(sparkline) >= 3:
                delta = sparkline[-1] - sparkline[0]
                direction = "declining" if delta <= -0.08 else ("improving" if delta >= 0.08 else "stable")

            payload = {
                "engagement_health": {
                    "score": health.score,
                    "state": health.state,
                    "direction": direction,
                    "explanation": health.explanation,
                    "sparkline": sparkline,  # 0-1 daily series, oldest→newest
                }
            }

            fs = get_firestore_service()
            doc_ref = (
                fs.db.collection("workspaces")
                .document(_normalize_uuid(self.workspace_id))
                .collection("customer_insights")
                .document(_normalize_uuid(customer_id))
            )
            doc_ref.set(payload, merge=True)
        except Exception as e:
            logger.warning("engagement_health_cache_failed", customer_id=customer_id, error=str(e))

    async def _snapshot_velocity_metrics(self, customer_id: str) -> None:
        """Snapshot milestone velocity + stakeholder-graph health (best-effort)."""
        from datetime import date
        from services.velocity_metrics import compute_milestone_velocity, compute_stakeholder_graph
        from services import metric_snapshots

        # Milestone velocity
        try:
            mres = await self.dc.execute_query(
                "GetCustomerMilestonesForVelocity",
                {"workspaceId": self.workspace_id, "customerId": customer_id},
            )
            vel = compute_milestone_velocity(mres.get("milestones", []) or [], date.today())
            if vel.score is not None:
                await metric_snapshots.append_snapshot(
                    workspace_id=self.workspace_id, customer_id=customer_id,
                    metric="milestone_velocity", value=vel.score, trigger="scheduled_daily",
                    inputs={"on_track": vel.on_track, "overdue": vel.overdue,
                            "max_days_behind": vel.max_days_behind, "detail": vel.detail},
                )
        except Exception as e:
            logger.warning("milestone_velocity_failed", customer_id=customer_id, error=str(e))

        # Stakeholder-graph health
        try:
            sres = await self.dc.execute_query(
                "GetCustomerStakeholders", {"customerId": customer_id}
            )
            stakeholders = (sres.get("customer") or {}).get("stakeholders_on_customer", []) or []
            graph = compute_stakeholder_graph(stakeholders)
            if graph.score is not None:
                await metric_snapshots.append_snapshot(
                    workspace_id=self.workspace_id, customer_id=customer_id,
                    metric="stakeholder_graph", value=graph.score, trigger="scheduled_daily",
                    inputs={"active_contacts": graph.active_contacts,
                            "active_champions": graph.active_champions,
                            "single_point_of_failure": graph.single_point_of_failure,
                            "detail": graph.detail},
                )
        except Exception as e:
            logger.warning("stakeholder_graph_failed", customer_id=customer_id, error=str(e))

    async def _persist_finding(self, finding: SweepFinding) -> bool:
        """Write a Signal row. Returns True if created, False if deduped."""
        # Final dedup: check inputs_hash against existing signals
        # (catches race conditions between detectors and between runs)
        existing = await self.dc.execute_query(
            "GetActiveSignalByKind",
            {
                "workspaceId": self.workspace_id,
                "customerId": finding.customer_id,
                "kind": finding.signal_kind,
            },
        )
        if existing.get("signals"):
            existing_signal = existing["signals"][0]
            # Allow escalation from warn → risk to pass through
            if existing_signal.get("state") == finding.signal_state:
                return False
            if existing_signal.get("state") == "risk":
                return False

        signal_id = str(uuid4())
        await self.dc.execute_mutation(
            "CreateSignalWithId",
            {
                "id": signal_id,
                "workspaceId": self.workspace_id,
                "customerId": finding.customer_id,
                "kind": finding.signal_kind,
                "state": finding.signal_state,
                "sentence": finding.sentence,
                "evidenceText": finding.evidence_text,
                "model": "sweep",
                "promptVersion": "1.0",
                "inputsHash": finding.inputs_hash,
                "handbookVersionId": _HANDBOOK_PLACEHOLDER,
            },
        )

        logger.info(
            "sweep_signal_created",
            signal_id=signal_id,
            customer_id=finding.customer_id,
            customer_name=finding.customer_name,
            kind=finding.signal_kind,
            state=finding.signal_state,
        )

        # Route to orchestrator queue if warranted
        from services.signal_router import route_signal
        await route_signal(
            workspace_id=self.workspace_id,
            customer_id=finding.customer_id,
            signal_id=signal_id,
            signal_kind=finding.signal_kind,
            signal_state=finding.signal_state,
            signal_sentence=finding.sentence,
        )

        return True

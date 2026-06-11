"""
Metric Snapshots Service

Append-only time-series log for tracked customer scores and states — the durable
substrate from docs/plans/SIGNAL_AGGREGATION.md. Implements "append-on-change":
every recalculation of a tracked metric appends a row capturing the new value,
the prior value, what triggered the change, and the contributing inputs. Nothing
is ever overwritten; the current-value fields on Customer/ProgressVector remain
the fast "what is it now" read, this log is the "how did it get here" history.

Discipline:
  - Feature-flagged: every write/read is a no-op when METRIC_SNAPSHOTS_ENABLED is
    False — the backend then behaves exactly as before this feature existed.
  - Best-effort: writes never raise into their callers (health scoring, vector
    consolidation). Exceptions are logged and swallowed, mirroring the Firestore
    write pattern in customer_insights_service.py.

Metric catalog (String, not enum, so it can grow without a schema migration):
  health_score       — Customer.relationshipHealthScore (0-100)
  engagement         — account-level engagement score (0.0-1.0)
  sentiment          — account-level sentiment score (0.0-1.0)
  engagement_health  — derived composite going-dark health (0.0-1.0)
  vector_<category>  — ProgressVector currentState (ok/warn/risk) per category
                       e.g. vector_trust, vector_value, vector_momentum,
                            vector_stakeholder, vector_risk_mitigation

Trigger catalog:
  scheduled_daily    — sweep heartbeat (evenly-spaced sample)
  risk_signal        — a risk signal fired / play triggered the recompute
  commitment_change  — a commitment status changed
  play_completed     — an orchestrator play finished
  manual_override    — a user directly edited the value
  inbound            — inbound re-engagement
  sweep              — general sweep (non-daily-specific)
  assessment         — progress-vector assessment after memory consolidation

Retention: append-on-change is chatty for active accounts. Rows are small; the
plan is to keep raw rows for a recent window (~90 days) and downsample older
history to daily. Downsampling is a future background job — capturedAt is its
key. The 200-row limit on GetRecentMetricSnapshots reflects that 90-day window.
"""

import json
from typing import Any

from config import get_settings
from core.logging import get_logger
from db.dataconnect_client import get_dataconnect_client

logger = get_logger("MetricSnapshots")

# ---------------------------------------------------------------------------
# Catalog discipline. String metric/trigger values keep the schema stable as the
# catalog grows, but drift is real — so we keep the known sets here. Unknown
# values are logged (observable in logs) but still written: never silently drop.
# When adding a value, update BOTH the frozenset and the module docstring.
# ---------------------------------------------------------------------------

KNOWN_METRICS: frozenset[str] = frozenset({
    "health_score",
    "engagement",
    "sentiment",
    "engagement_health",
    "response_latency",   # per-stakeholder reply latency in hours (stakeholder-scoped)
    "commitment_reliability_us",    # our follow-through rate (0-1)
    "commitment_reliability_them",  # their follow-through rate (0-1)
    "milestone_velocity",           # onboarding/milestone on-track score (0-1)
    "stakeholder_graph",            # relationship breadth / champion coverage (0-1)
    "vector_trust",
    "vector_risk_mitigation",
    "vector_stakeholder",
    "vector_value",
    "vector_momentum",
})

KNOWN_TRIGGERS: frozenset[str] = frozenset({
    "scheduled_daily",
    "risk_signal",
    "commitment_change",
    "play_completed",
    "manual_override",
    "inbound",
    "sweep",
    "assessment",
})


# ---------------------------------------------------------------------------
# Write path
# ---------------------------------------------------------------------------


async def append_snapshot(
    workspace_id: str,
    customer_id: str,
    metric: str,
    *,
    trigger: str,
    inputs: dict[str, Any],
    value: float | None = None,
    state: str | None = None,
    prev_value: float | None = None,
    stakeholder_id: str | None = None,
) -> None:
    """Append one MetricSnapshot row.

    No-op (returns immediately) when METRIC_SNAPSHOTS_ENABLED is False.
    Never raises — exceptions are logged and swallowed so a snapshot failure
    can never break the health-score or vector write it rides alongside.

    Args:
        workspace_id:   Workspace UUID string.
        customer_id:    Customer UUID string.
        metric:         Catalog key (e.g. "health_score", "vector_trust").
        trigger:        What caused this append (catalog key).
        inputs:         Contributing factors — JSON-serialized. Pass {} not None.
        value:          Numeric value where applicable; None for state-only metrics.
        state:          "ok" | "warn" | "risk" where applicable; None otherwise.
        prev_value:     Prior numeric value, or None when no prior snapshot exists.
                        (0 is a valid score, so None — not 0 — is the "no baseline"
                        sentinel.) Use get_latest() to populate this when needed.
        stakeholder_id: Optional stakeholder UUID for per-stakeholder metrics.
    """
    if not get_settings().metric_snapshots_enabled:
        return

    if metric not in KNOWN_METRICS:
        logger.warning("metric_snapshot_unknown_metric", metric=metric, customer_id=customer_id)
    if trigger not in KNOWN_TRIGGERS:
        logger.warning("metric_snapshot_unknown_trigger", trigger=trigger, customer_id=customer_id)

    try:
        dc = get_dataconnect_client()
        await dc.execute_mutation(
            "CreateMetricSnapshot",
            {
                "workspaceId": workspace_id,
                "customerId": customer_id,
                "stakeholderId": stakeholder_id,
                "metric": metric,
                "value": value,
                "state": state,
                "prevValue": prev_value,
                "trigger": trigger,
                "inputs": json.dumps(inputs, default=str),
            },
        )
        logger.debug(
            "metric_snapshot_appended",
            workspace_id=workspace_id,
            customer_id=customer_id,
            metric=metric,
            value=value,
            state=state,
            trigger=trigger,
        )
    except Exception as e:
        # Best-effort: never propagate into the caller's write path.
        logger.error(
            "metric_snapshot_write_failed",
            workspace_id=workspace_id,
            customer_id=customer_id,
            metric=metric,
            trigger=trigger,
            error=str(e),
        )


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


async def get_latest(
    workspace_id: str,
    customer_id: str,
    metric: str,
) -> dict[str, Any] | None:
    """Return the most recent snapshot row for a customer/metric, or None.

    Returns None (never raises) when the flag is off, on any error, or when no
    snapshot exists yet. Used to read prev_value before an append_snapshot call.
    """
    if not get_settings().metric_snapshots_enabled:
        return None

    try:
        dc = get_dataconnect_client()
        result = await dc.execute_query(
            "GetLatestMetricSnapshot",
            {"workspaceId": workspace_id, "customerId": customer_id, "metric": metric},
        )
        rows = result.get("metricSnapshots", [])
        return rows[0] if rows else None
    except Exception as e:
        logger.warning(
            "metric_snapshot_latest_read_failed",
            workspace_id=workspace_id,
            customer_id=customer_id,
            metric=metric,
            error=str(e),
        )
        return None


async def get_recent_for_stakeholder(
    workspace_id: str,
    stakeholder_id: str,
    metric: str,
    since_iso: str,
) -> list[dict[str, Any]]:
    """Return a single stakeholder's snapshots for a metric since an ISO timestamp.

    Oldest-first. Used for per-stakeholder responsiveness baselines. Returns [] when
    the flag is off or on any error.
    """
    if not get_settings().metric_snapshots_enabled:
        return []

    try:
        dc = get_dataconnect_client()
        result = await dc.execute_query(
            "GetRecentStakeholderMetricSnapshots",
            {
                "workspaceId": workspace_id,
                "stakeholderId": stakeholder_id,
                "metric": metric,
                "since": since_iso,
            },
        )
        return result.get("metricSnapshots", [])
    except Exception as e:
        logger.warning(
            "metric_snapshot_stakeholder_read_failed",
            workspace_id=workspace_id,
            stakeholder_id=stakeholder_id,
            metric=metric,
            error=str(e),
        )
        return []


async def get_recent(
    workspace_id: str,
    customer_id: str,
    metric: str,
    since_iso: str,
) -> list[dict[str, Any]]:
    """Return snapshots for a customer/metric since an ISO 8601 timestamp.

    Oldest-first (suitable for sparklines / trend direction). Returns [] when the
    flag is off or on any error.

    Args:
        since_iso: ISO 8601 string, e.g. "2026-03-01T00:00:00+00:00".
    """
    if not get_settings().metric_snapshots_enabled:
        return []

    try:
        dc = get_dataconnect_client()
        result = await dc.execute_query(
            "GetRecentMetricSnapshots",
            {
                "workspaceId": workspace_id,
                "customerId": customer_id,
                "metric": metric,
                "since": since_iso,
            },
        )
        return result.get("metricSnapshots", [])
    except Exception as e:
        logger.warning(
            "metric_snapshot_recent_read_failed",
            workspace_id=workspace_id,
            customer_id=customer_id,
            metric=metric,
            error=str(e),
        )
        return []

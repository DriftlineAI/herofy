"""
Per-stakeholder responsiveness — the leading going-dark indicator.

When an inbound reply arrives that answers one of our outbound messages in the
same thread, we pair them and record the response latency, attributed to the
replying stakeholder (docs/plans/ENGAGEMENT_HEALTH_MODEL.md). Persisting these as
MetricSnapshots builds the rolling history needed to see "this champion who used
to reply in a day is now taking a week" — a deviation we cannot detect from
point-in-time data.

This module owns the capture (record_response_latency, called from the inbound
write path) and the baseline/deviation read (responsiveness_deviation, used by the
contact-level engagement health in chunk 2b).

Flag-gated + best-effort: no-ops and never raises when METRIC_SNAPSHOTS_ENABLED is off.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from config import get_settings
from core.logging import get_logger
from db.dataconnect_client import get_dataconnect_client
from services import metric_snapshots

logger = get_logger("Responsiveness")

# A reply that lands more than this long after our message is treated as a fresh
# outreach, not a "response" — pairing it would pollute the latency baseline.
_MAX_PAIR_HOURS = 14 * 24  # 14 days

# Deviation detection (the "1 fluke / 2 coincidence / 3 pattern" shape — k tunable).
_DEVIATION_STREAK = 3          # how many recent latencies must run high together
_DEVIATION_MULTIPLIER = 2.0    # "materially above baseline" = ≥ this × the baseline
_MIN_BASELINE_SAMPLES = 3      # need at least this much history to have a baseline
_EWMA_ALPHA = 0.4              # weight on newer samples in the baseline EWMA


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def compute_pair_latency_hours(outbound_at_iso: str | None, inbound_at_iso: str | None) -> float | None:
    """Pure: latency in hours between our outbound and the inbound reply, or None when
    unpairable — unparseable timestamps, negative (clock skew), or older than the max
    pairing window (a reply that late is fresh outreach, not a response)."""
    outbound = _parse_ts(outbound_at_iso)
    inbound = _parse_ts(inbound_at_iso)
    if outbound is None or inbound is None:
        return None
    hours = (inbound - outbound).total_seconds() / 3600.0
    if hours < 0 or hours > _MAX_PAIR_HOURS:
        return None
    return round(hours, 2)


async def record_response_latency(
    workspace_id: str,
    customer_id: str,
    thread_id: str | None,
    stakeholder_id: str | None,
    inbound_at_iso: str,
) -> float | None:
    """Pair an inbound reply to our last outbound in the same thread and record the
    latency (hours) as a per-stakeholder MetricSnapshot.

    No-op (returns None) when the flag is off, when there's no thread/stakeholder to
    attribute to, or when no preceding outbound exists. Never raises.

    Returns the latency in hours when a pair was recorded, else None.
    """
    if not get_settings().metric_snapshots_enabled:
        return None
    if not thread_id or not stakeholder_id:
        return None  # can't attribute responsiveness without both

    if _parse_ts(inbound_at_iso) is None:
        return None

    try:
        dc = get_dataconnect_client()
        result = await dc.execute_query(
            "GetLastOutboundInThreadBefore",
            {"threadId": thread_id, "before": inbound_at_iso},
        )
        rows = result.get("interactions", [])
        if not rows:
            return None  # they reached out unprompted — not a response to pair

        latency_hours = compute_pair_latency_hours(rows[0].get("occurredAt"), inbound_at_iso)
        if latency_hours is None:
            return None  # unparseable / negative (clock skew) / too old to be a genuine reply

        await metric_snapshots.append_snapshot(
            workspace_id=workspace_id,
            customer_id=customer_id,
            metric="response_latency",
            value=round(latency_hours, 2),
            trigger="inbound",
            inputs={
                "thread_id": thread_id,
                "outbound_at": rows[0].get("occurredAt"),
                "inbound_at": inbound_at_iso,
            },
            stakeholder_id=stakeholder_id,
        )
        logger.debug(
            "response_latency_recorded",
            customer_id=customer_id,
            stakeholder_id=stakeholder_id,
            latency_hours=round(latency_hours, 2),
        )
        return latency_hours
    except Exception as e:
        logger.warning("response_latency_capture_failed", stakeholder_id=stakeholder_id, error=str(e))
        return None


_BREADTH_WINDOW_DAYS = 30  # a key contact counts as "active" if seen within this window


async def gather_contact_signals(workspace_id: str, customer_id: str, lifecycle: str):
    """Assemble the contact-level overlay for compute_engagement_health: champion
    silence, responsiveness decay on key contacts, and engagement breadth.

    Returns a ContactSignals, or None when there's no stakeholder data (so the model
    falls back to pure account-level scoring — never worse than today). Importance
    falls back to isChampion when the structured tier hasn't been set. Never raises.
    """
    if not get_settings().metric_snapshots_enabled:
        return None

    from services.engagement_health_service import ContactSignals, LIFECYCLE_THRESHOLDS

    threshold = LIFECYCLE_THRESHOLDS.get(lifecycle, 7)

    try:
        dc = get_dataconnect_client()
        result = await dc.execute_query("GetCustomerStakeholders", {"customerId": customer_id})
        stakeholders = (result.get("customer") or {}).get("stakeholders_on_customer", []) or []
    except Exception as e:
        logger.warning("contact_signals_fetch_failed", customer_id=customer_id, error=str(e))
        return None

    active = [s for s in stakeholders if (s.get("status") or "active") == "active"]
    if not active:
        return None

    now = datetime.now(timezone.utc)

    def _is_champion(s) -> bool:
        return s.get("importance") == "champion" or bool(s.get("isChampion"))

    def _is_key(s) -> bool:
        return _is_champion(s) or s.get("importance") in ("economic_buyer", "technical")

    def _days_since(s) -> int | None:
        ts = _parse_ts(s.get("lastInteractionAt"))
        return (now - ts).days if ts else None

    champions = [s for s in active if _is_champion(s)]
    key_contacts = [s for s in active if _is_key(s)]

    champ_days = [d for d in (_days_since(s) for s in champions) if d is not None]
    champion_silent_days = min(champ_days) if champ_days else None

    active_key = sum(
        1 for s in key_contacts
        if (_days_since(s) is not None and _days_since(s) <= _BREADTH_WINDOW_DAYS)
    )

    # Responsiveness decay across key contacts (first deviating contact wins for the label).
    responsiveness_deviated = False
    deviating_name: str | None = None
    for s in key_contacts:
        verdict = await responsiveness_deviation(workspace_id, str(s["id"]))
        if verdict.deviated:
            responsiveness_deviated = True
            deviating_name = s.get("name")
            break

    detail: list[str] = []
    if champion_silent_days is not None and champion_silent_days >= threshold:
        detail.append(f"champion silent {champion_silent_days}d")
    if responsiveness_deviated:
        detail.append(f"{deviating_name or 'key contact'} responsiveness decaying")
    if key_contacts and active_key == 0:
        detail.append(f"no key contacts active in {_BREADTH_WINDOW_DAYS}d")

    return ContactSignals(
        champion_silent_days=champion_silent_days,
        champion_threshold_days=threshold,
        responsiveness_deviated=responsiveness_deviated,
        active_key_contacts=active_key,
        total_key_contacts=len(key_contacts),
        detail=detail,
    )


async def suggest_ooo_delegate(
    workspace_id: str,
    customer_id: str,
    absent_stakeholder_id: str,
    *,
    until: str | None,
    delegate_name: str | None,
    delegate_email: str | None,
) -> None:
    """Opportunistically surface an OOO delegate as a tip so the CSM can add them to
    the contact graph (the human-as-tool pattern, lightweight form).

    Skips when the delegate is already a known stakeholder (by email). Best-effort —
    never raises into the inbound path. The interactive add-and-redirect loop is a
    follow-up; this records the actionable suggestion in the RightRail activity feed.
    """
    try:
        dc = get_dataconnect_client()

        # Already known? (only checkable when the auto-reply included an email)
        if delegate_email:
            existing = await dc.execute_query(
                "GetStakeholderByEmail",
                {"workspaceId": workspace_id, "email": delegate_email.lower()},
            )
            if existing.get("stakeholders"):
                return  # delegate already in the graph — nothing to suggest

        who = delegate_name or delegate_email or "a colleague"
        contact_bits = []
        if delegate_name and delegate_email:
            contact_bits.append(f"{delegate_name} ({delegate_email})")
        elif delegate_email:
            contact_bits.append(delegate_email)
        else:
            contact_bits.append(who)
        back = f", back {until}" if until else ""
        text = (
            f"Out-of-office auto-reply{back}: names {contact_bits[0]} as covering. "
            f"Consider adding them as a contact and redirecting in-flight outreach."
        )

        from orchestrator.artifacts import record_observation

        await record_observation(
            workspace_id=workspace_id,
            customer_id=customer_id,
            text=text,
            agent_run_id=None,
            kind="tip",
        )
        logger.info(
            "ooo_delegate_suggested",
            customer_id=customer_id,
            absent_stakeholder_id=absent_stakeholder_id,
            delegate=delegate_name or delegate_email,
        )
    except Exception as e:
        logger.warning("ooo_delegate_suggest_failed", customer_id=customer_id, error=str(e))


@dataclass
class ResponsivenessVerdict:
    """Result of responsiveness_deviation for one stakeholder."""

    deviated: bool             # True = recent replies materially slower than baseline
    baseline_hours: float | None
    recent_hours: list[float]  # the recent window, oldest→newest
    samples: int
    explanation: str


async def responsiveness_deviation(
    workspace_id: str,
    stakeholder_id: str,
    *,
    since_iso: str | None = None,
) -> ResponsivenessVerdict:
    """Read a stakeholder's recent response-latency snapshots and decide whether the
    recent streak is materially slower than their established baseline.

    Baseline = EWMA over the latencies preceding the recent window. Deviation fires
    when the last `_DEVIATION_STREAK` latencies are ALL ≥ `_DEVIATION_MULTIPLIER`×
    baseline (the fluke→coincidence→pattern shape). Degrades gracefully: too little
    history → not deviated. Never raises.
    """
    if not get_settings().metric_snapshots_enabled:
        return ResponsivenessVerdict(False, None, [], 0, "insufficient history")

    if since_iso is None:
        from datetime import timedelta
        since_iso = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()

    snaps = await metric_snapshots.get_recent_for_stakeholder(
        workspace_id, stakeholder_id, "response_latency", since_iso
    )
    # Latencies oldest→newest (query returns ASC by capturedAt).
    values = [s["value"] for s in snaps if s.get("value") is not None]
    return evaluate_latencies(values)


def evaluate_latencies(values: list[float]) -> ResponsivenessVerdict:
    """Pure deviation logic over a stakeholder's latencies (oldest→newest).

    Baseline = EWMA over the latencies preceding the recent streak. Deviation fires
    when the last `_DEVIATION_STREAK` latencies are ALL ≥ `_DEVIATION_MULTIPLIER`×
    baseline. Too little history → not deviated (graceful).
    """
    if len(values) < _MIN_BASELINE_SAMPLES + _DEVIATION_STREAK:
        return ResponsivenessVerdict(
            False, None, values[-_DEVIATION_STREAK:], len(values), "insufficient history"
        )

    recent = values[-_DEVIATION_STREAK:]
    prior = values[: -_DEVIATION_STREAK]

    # EWMA baseline over the prior latencies.
    baseline = prior[0]
    for v in prior[1:]:
        baseline = _EWMA_ALPHA * v + (1 - _EWMA_ALPHA) * baseline

    deviated = baseline > 0 and all(r >= _DEVIATION_MULTIPLIER * baseline for r in recent)
    if deviated:
        explanation = (
            f"replies running {recent[-1]:.0f}h vs ~{baseline:.0f}h baseline "
            f"({_DEVIATION_STREAK} in a row ≥ {_DEVIATION_MULTIPLIER:g}×)"
        )
    else:
        explanation = f"baseline ~{baseline:.0f}h, recent {recent[-1]:.0f}h — within range"

    return ResponsivenessVerdict(
        deviated=deviated,
        baseline_hours=round(baseline, 2),
        recent_hours=[round(r, 2) for r in recent],
        samples=len(values),
        explanation=explanation,
    )

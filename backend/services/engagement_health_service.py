"""
Engagement Health Service

Computes a 0-1 derived engagement-health score — the account-level "going dark"
signal as a DERIVED FUNCTION over trend data, per docs/plans/ENGAGEMENT_HEALTH_MODEL.md.

The core reframe: silence only matters relative to what is normal for THIS account.
A flat days-since-contact threshold flags every account "dark" identically; the
derived score instead blends recency (vs the account's lifecycle norm), cadence
(this account's own volume baseline), and sentiment trajectory — so it can catch
the "cadence + sentiment slipping but not yet fully silent" case the flat
threshold misses, while staying no worse than the flat backbone when data is sparse.

Phase-0 scope (account-level only): the composition takes primitives that ALREADY
exist today — it invents no new scoring. Per-stakeholder responsiveness (the
leading indicator) is deferred until the Interaction→Stakeholder linkage lands.

This module is a PURE function (no DB, no async): the caller pre-computes the
primitives (the sweep heartbeat reads them off an already-computed CustomerInsight)
and persists the result as a MetricSnapshot (metric="engagement_health").
"""

from dataclasses import dataclass
from typing import Any

from core.logging import get_logger

logger = get_logger("EngagementHealthService")

# Lifecycle-specific days-silent thresholds — the single source of truth shared
# by the flat GoingDarkDetector (imported there as _GOING_DARK_THRESHOLDS) and the
# derived score here, so the two use the same "what's normal for this lifecycle"
# baseline and can never silently diverge.
LIFECYCLE_THRESHOLDS: dict[str, int] = {
    "onboarding": 4,   # tighter SLA during onboarding
    "handoff": 3,
    "active": 7,
    "renewing": 5,     # extra vigilance near renewal
    "at_risk": 3,      # already flagged, watch closely
}
_DEFAULT_THRESHOLD = 7

# Lifecycle weight: tighter lifecycles amplify the recency penalty (silence near
# renewal / on an at-risk account matters more than on a steady-state account).
_LIFECYCLE_WEIGHT: dict[str, float] = {
    "onboarding": 1.2,
    "handoff": 1.0,
    "active": 1.0,
    "renewing": 1.4,
    "at_risk": 1.4,
}

# Component weights — must sum to 1.0. Recency dominates (most reliable at Phase 0);
# cadence captures the trend without stakeholder resolution; sentiment adds color.
_W_RECENCY = 0.44
_W_CADENCE = 0.33
_W_SENTIMENT = 0.23

# Neutral fallback used when a component has no data — pulls the composite toward
# center so data ABSENCE alone never makes the system more alarmed than it should be.
_NEUTRAL = 0.5


# Contact-level penalty weights — how much each high-severity contact signal pulls
# the account score down (additive, bounded). Champion silence and responsiveness
# decay are the renewal-killers the flat account view misses.
_P_CHAMPION_SILENT = 0.25
_P_RESPONSIVENESS = 0.20
_P_BREADTH_COLLAPSE = 0.15


@dataclass
class EngagementHealthResult:
    """Output of compute_engagement_health()."""

    score: float                 # 0.0 (dark / at-risk) – 1.0 (healthy / engaged)
    state: str                   # "ok" | "warn" | "risk" (maps to Signal.state)
    components: dict[str, float]  # per-component 0-1 scores (explainability)
    inputs: dict[str, Any]        # full inputs dict for MetricSnapshot.inputs + AI context
    explanation: str             # one-liner for Signal.sentence / AI context
    confidence: float            # 0-1; degrades as components go missing


@dataclass
class ContactSignals:
    """Contact-level inputs that SHARPEN the account composite (additive, never a
    gate). All optional — absent contact data degrades to pure account-level scoring,
    never worse than today. Assembled by responsiveness.gather_contact_signals()."""

    champion_silent_days: int | None   # days since the most-recently-active champion (None = no champion / unknown)
    champion_threshold_days: int       # lifecycle silence threshold to compare against
    responsiveness_deviated: bool      # a key contact's replies are materially slowing
    active_key_contacts: int           # breadth: key contacts active in the window
    total_key_contacts: int            # total key contacts known
    detail: list[str]                  # human-readable fragments for the explanation


def _state_for(score: float, lifecycle: str) -> str:
    """Map a composite score to ok/warn/risk (tighter for at_risk/renewing)."""
    if lifecycle in ("at_risk", "renewing"):
        return "risk" if score < 0.35 else ("warn" if score < 0.55 else "ok")
    return "risk" if score < 0.30 else ("warn" if score < 0.50 else "ok")


def compute_engagement_health(
    *,
    lifecycle: str,
    days_since_last: int | None,
    cadence_ratio: float | None,
    sentiment_score: float | None,
    sentiment_direction: str | None,
    contact: "ContactSignals | None" = None,
) -> EngagementHealthResult:
    """Compose the 0-1 engagement-health score from account-level primitives.

    Pure synchronous computation — no DB calls. Any missing component degrades
    gracefully: it contributes the neutral 0.5 and lowers the confidence score.

    Args:
        lifecycle:           Customer lifecycle (onboarding/active/renewing/at_risk/…).
        days_since_last:     Days since the last interaction (None = no contact ever).
        cadence_ratio:       Recent inbound volume / prior-window volume. ~1.0 = steady,
                             <1.0 = slowing, None = no baseline to compare against.
        sentiment_score:     Already-normalized 0-1 sentiment (None = no data).
        sentiment_direction: "improving" | "stable" | "declining" (None = no data).

    Returns:
        EngagementHealthResult with score, state, per-component scores, inputs,
        a human-readable explanation, and a confidence value.
    """
    threshold = LIFECYCLE_THRESHOLDS.get(lifecycle, _DEFAULT_THRESHOLD)
    lc_weight = _LIFECYCLE_WEIGHT.get(lifecycle, 1.0)
    missing: list[str] = []

    # ── Component 1: Recency ────────────────────────────────────────────────
    # 0 days → 1.0; at threshold → ~0.5; at 2× threshold (lifecycle-weighted) → 0.0.
    if days_since_last is not None:
        norm = (days_since_last / threshold) * lc_weight
        recency_score = max(0.0, 1.0 - norm / 2.0)
        recency_data: dict[str, Any] = {"days_since_last": days_since_last, "threshold_days": threshold}
    else:
        recency_score = 0.0  # no contact ever — worst case
        recency_data = {"days_since_last": None, "threshold_days": threshold}
        missing.append("recency")

    # ── Component 2: Cadence vs this account's own baseline ──────────────────
    # ratio >= 1.0 → 1.0 (a surge is not risk); 0.5 → 0.5; 0 → 0.0.
    if cadence_ratio is not None:
        cadence_score = max(0.0, min(1.0, cadence_ratio))
        pct_drop = int((1.0 - cadence_score) * 100) if cadence_score < 1.0 else 0
        cadence_data: dict[str, Any] = {"ratio": round(cadence_ratio, 2), "pct_drop": pct_drop}
    else:
        cadence_score = _NEUTRAL
        cadence_data = {"ratio": None, "pct_drop": None}
        missing.append("cadence")

    # ── Component 3: Sentiment trajectory ────────────────────────────────────
    # Base on the normalized sentiment score, nudged by trend direction.
    if sentiment_score is not None:
        direction_adj = {"improving": 0.10, "stable": 0.0, "declining": -0.15}.get(
            sentiment_direction or "stable", 0.0
        )
        sentiment_component = max(0.0, min(1.0, sentiment_score + direction_adj))
        sentiment_data: dict[str, Any] = {
            "score": round(sentiment_score, 2),
            "direction": sentiment_direction,
        }
    else:
        sentiment_component = _NEUTRAL
        sentiment_data = {"score": None, "direction": sentiment_direction}
        missing.append("sentiment")

    # ── Composite ─────────────────────────────────────────────────────────────
    raw = (
        _W_RECENCY * recency_score
        + _W_CADENCE * cadence_score
        + _W_SENTIMENT * sentiment_component
    )
    score = round(max(0.0, min(1.0, raw)), 3)
    state = _state_for(score, lifecycle)

    # ── Human-readable explanation (for Signal.sentence + AI context) ─────────
    parts: list[str] = []
    if days_since_last is not None:
        if days_since_last >= threshold:
            parts.append(f"silent {days_since_last}d (threshold {threshold}d)")
        else:
            parts.append(f"last contact {days_since_last}d ago")
    if cadence_data.get("pct_drop"):
        parts.append(f"cadence -{cadence_data['pct_drop']}% vs baseline")
    if sentiment_data.get("direction") == "declining":
        parts.append("sentiment declining")
    elif sentiment_data.get("direction") == "improving":
        parts.append("sentiment improving")

    # ── Contact-level overlay (additive; absent contact data = pure account view) ──
    # Champion silence and responsiveness decay are renewal-killers the account view
    # misses, so they apply a bounded penalty AND raise the state floor.
    contact_data: dict[str, Any] | None = None
    if contact is not None:
        champion_silent = (
            contact.champion_silent_days is not None
            and contact.champion_silent_days >= contact.champion_threshold_days
        )
        breadth_collapse = contact.total_key_contacts > 0 and contact.active_key_contacts == 0
        penalty = 0.0
        if champion_silent:
            penalty += _P_CHAMPION_SILENT
        if contact.responsiveness_deviated:
            penalty += _P_RESPONSIVENESS
        if breadth_collapse:
            penalty += _P_BREADTH_COLLAPSE

        if penalty > 0:
            score = round(max(0.0, score - penalty), 3)
            state = _state_for(score, lifecycle)
            # High-severity floor: champion silence / responsiveness decay never read
            # as "ok"; compounded signals escalate to risk.
            if champion_silent or contact.responsiveness_deviated:
                if state == "ok":
                    state = "warn"
                if champion_silent and (contact.responsiveness_deviated or breadth_collapse):
                    state = "risk"
            parts.extend(contact.detail)

        contact_data = {
            "champion_silent_days": contact.champion_silent_days,
            "champion_threshold_days": contact.champion_threshold_days,
            "responsiveness_deviated": contact.responsiveness_deviated,
            "active_key_contacts": contact.active_key_contacts,
            "total_key_contacts": contact.total_key_contacts,
            "penalty": round(penalty, 3),
        }

    explanation = "; ".join(parts) if parts else f"lifecycle={lifecycle}, score={score}"

    # ── Confidence: full when all 3 account components have data; -0.25 each missing.
    # Contact data, when present, nudges confidence up (a sharper picture).
    confidence = round(max(0.1, 1.0 - 0.25 * len(missing)), 2)
    if contact_data is not None and contact.total_key_contacts > 0:
        confidence = round(min(1.0, confidence + 0.1), 2)

    components = {
        "recency": round(recency_score, 3),
        "cadence": round(cadence_score, 3),
        "sentiment": round(sentiment_component, 3),
    }
    inputs = {
        "lifecycle": lifecycle,
        # raw factor detail (what drove each component) — the explainability payload
        "recency": recency_data,
        "cadence": cadence_data,
        "sentiment": sentiment_data,
        # the 0-1 component scores themselves, persisted so the snapshot is
        # self-contained for the AI-context read-back (_build_engagement_health_block)
        "component_scores": components,
        "weights": {"recency": _W_RECENCY, "cadence": _W_CADENCE, "sentiment": _W_SENTIMENT},
        "lifecycle_weight": lc_weight,
        "missing_components": missing,
        # contact-level overlay (None when no stakeholder data was available)
        "contact": contact_data,
        # 'explanation' is intentionally duplicated here (also on the dataclass) so a
        # persisted snapshot can be explained without rehydrating the full result.
        "explanation": explanation,
    }

    logger.debug(
        "engagement_health_computed",
        lifecycle=lifecycle,
        score=score,
        state=state,
        recency=components["recency"],
        cadence=components["cadence"],
        sentiment=components["sentiment"],
        missing=missing,
    )

    return EngagementHealthResult(
        score=score,
        state=state,
        components=components,
        inputs=inputs,
        explanation=explanation,
        confidence=confidence,
    )

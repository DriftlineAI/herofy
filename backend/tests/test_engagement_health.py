"""
Unit tests for the engagement-health composition function.

compute_engagement_health is a PURE function (no DB, no async), so these tests
need no fixtures — they just assert the score/state/degradation behavior across
the cases the model is designed to handle (see docs/plans/ENGAGEMENT_HEALTH_MODEL.md).
"""

from services.engagement_health_service import compute_engagement_health, ContactSignals


def test_healthy_account_is_ok():
    r = compute_engagement_health(
        lifecycle="active",
        days_since_last=1,
        cadence_ratio=1.1,
        sentiment_score=0.8,
        sentiment_direction="stable",
    )
    assert r.state == "ok"
    assert r.score > 0.65
    assert r.confidence == 1.0
    assert r.inputs["missing_components"] == []


def test_selective_engagement_flags_warn_below_flat_threshold():
    """The case the flat days-since-contact threshold MISSES: not silent yet
    (4d < active's 7d), but cadence collapsed and sentiment declining."""
    r = compute_engagement_health(
        lifecycle="active",
        days_since_last=4,
        cadence_ratio=0.35,
        sentiment_score=0.4,
        sentiment_direction="declining",
    )
    assert r.state in ("warn", "risk")
    assert "cadence" in r.explanation and "sentiment declining" in r.explanation


def test_fully_silent_account_is_risk():
    r = compute_engagement_health(
        lifecycle="active",
        days_since_last=16,
        cadence_ratio=0.0,
        sentiment_score=0.3,
        sentiment_direction="declining",
    )
    assert r.state == "risk"
    assert r.score < 0.30


def test_at_risk_lifecycle_tightens_thresholds():
    """An at_risk account crosses to risk on milder degradation than a steady one."""
    kwargs = dict(days_since_last=4, cadence_ratio=0.6, sentiment_score=0.5, sentiment_direction="stable")
    at_risk = compute_engagement_health(lifecycle="at_risk", **kwargs)
    active = compute_engagement_health(lifecycle="active", **kwargs)
    assert at_risk.score < active.score  # tighter lifecycle weight penalizes more


def test_sparse_data_degrades_gracefully_not_alarmist():
    """Missing cadence + sentiment must not push a recently-contacted account to risk."""
    r = compute_engagement_health(
        lifecycle="active",
        days_since_last=3,
        cadence_ratio=None,
        sentiment_score=None,
        sentiment_direction=None,
    )
    assert r.state == "ok"
    assert r.confidence < 1.0
    assert set(r.inputs["missing_components"]) == {"cadence", "sentiment"}


def test_never_contacted_is_low_confidence_risk():
    r = compute_engagement_health(
        lifecycle="onboarding",
        days_since_last=None,
        cadence_ratio=None,
        sentiment_score=None,
        sentiment_direction=None,
    )
    assert r.state == "risk"
    assert r.confidence == 0.25  # all three components missing
    assert "recency" in r.inputs["missing_components"]


def test_contact_overlay_escalates_a_healthy_looking_account():
    """Champion silence + responsiveness decay must pull a healthy account into risk —
    the renewal-killer the account view alone misses."""
    contact = ContactSignals(
        champion_silent_days=12,
        champion_threshold_days=7,
        responsiveness_deviated=True,
        active_key_contacts=1,
        total_key_contacts=2,
        detail=["champion silent 12d", "Bob responsiveness decaying"],
    )
    healthy = compute_engagement_health(
        lifecycle="active", days_since_last=2, cadence_ratio=1.0,
        sentiment_score=0.8, sentiment_direction="stable", contact=None,
    )
    sharpened = compute_engagement_health(
        lifecycle="active", days_since_last=2, cadence_ratio=1.0,
        sentiment_score=0.8, sentiment_direction="stable", contact=contact,
    )
    assert healthy.state == "ok"                 # account-only view is fine
    assert sharpened.state in ("warn", "risk")   # contact overlay sharpens it
    assert sharpened.score < healthy.score
    assert "champion silent" in sharpened.explanation


def test_contact_overlay_absent_is_pure_account_view():
    """No contact data → identical to account-only (graceful degradation)."""
    base = compute_engagement_health(
        lifecycle="active", days_since_last=5, cadence_ratio=0.8,
        sentiment_score=0.6, sentiment_direction="stable", contact=None,
    )
    healthy_contact = ContactSignals(
        champion_silent_days=1, champion_threshold_days=7,
        responsiveness_deviated=False, active_key_contacts=3, total_key_contacts=3, detail=[],
    )
    with_ok_contact = compute_engagement_health(
        lifecycle="active", days_since_last=5, cadence_ratio=0.8,
        sentiment_score=0.6, sentiment_direction="stable", contact=healthy_contact,
    )
    # A healthy contact picture applies no penalty → same score as account-only.
    assert with_ok_contact.score == base.score


def test_score_is_bounded_and_components_present():
    r = compute_engagement_health(
        lifecycle="active",
        days_since_last=10,
        cadence_ratio=0.5,
        sentiment_score=0.5,
        sentiment_direction="stable",
    )
    assert 0.0 <= r.score <= 1.0
    assert set(r.components) == {"recency", "cadence", "sentiment"}
    assert all(0.0 <= v <= 1.0 for v in r.components.values())

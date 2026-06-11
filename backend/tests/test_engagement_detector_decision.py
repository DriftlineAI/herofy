"""Unit tests for the EngagementHealthDetector firing decision (pure, anti-double-fire)."""

from services.signal_sweep_service import decide_engagement_finding, _score_to_state


def test_ok_never_fires():
    assert decide_engagement_finding("ok", None, None, None) is None


def test_fires_when_no_existing_signals():
    assert decide_engagement_finding("warn", None, None, None) == "warn"
    assert decide_engagement_finding("risk", None, None, None) == "risk"


def test_pile_on_suppressed_when_both_flat_at_risk_and_only_warn():
    # going_dark + cadence already at risk; a derived 'warn' adds nothing.
    assert decide_engagement_finding("warn", "risk", "risk", None) is None


def test_risk_fires_even_when_both_flat_at_risk():
    # A derived 'risk' is still meaningful information (e.g. escalation context).
    assert decide_engagement_finding("risk", "risk", "risk", None) == "risk"


def test_warn_fires_when_only_one_flat_at_risk():
    # The selective-engagement case the flat detectors don't both catch.
    assert decide_engagement_finding("warn", "risk", None, None) == "warn"
    assert decide_engagement_finding("warn", None, "risk", None) == "warn"


def test_own_kind_dedup_skips_equal_state():
    assert decide_engagement_finding("warn", None, None, "warn") is None


def test_own_kind_dedup_skips_when_existing_is_risk():
    assert decide_engagement_finding("warn", None, None, "risk") is None


def test_warn_to_risk_escalation_passes_dedup():
    # An existing 'warn' engagement signal should not block a new 'risk'.
    assert decide_engagement_finding("risk", None, None, "warn") == "risk"


def test_score_to_state_buckets():
    assert _score_to_state(0.9) == "ok"
    assert _score_to_state(0.65) == "ok"
    assert _score_to_state(0.5) == "warn"
    assert _score_to_state(0.4) == "warn"
    assert _score_to_state(0.39) == "risk"
    assert _score_to_state(0.0) == "risk"

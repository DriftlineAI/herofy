"""
Unit tests for the per-stakeholder responsiveness deviation logic.

evaluate_latencies is pure (no DB / async), so these assert the fluke→coincidence→
pattern behavior directly. See docs/plans/ENGAGEMENT_HEALTH_MODEL.md.
"""

from services.responsiveness import evaluate_latencies, compute_pair_latency_hours


def test_pair_latency_basic_hours():
    assert compute_pair_latency_hours(
        "2026-01-01T08:00:00+00:00", "2026-01-01T20:00:00+00:00"
    ) == 12.0


def test_pair_latency_negative_is_unpairable():
    # Inbound before outbound (clock skew / mis-pair) → None.
    assert compute_pair_latency_hours(
        "2026-01-02T08:00:00+00:00", "2026-01-01T08:00:00+00:00"
    ) is None


def test_pair_latency_too_old_is_unpairable():
    # A "reply" 20 days later is fresh outreach, not a paired response (>14d cap).
    assert compute_pair_latency_hours(
        "2026-01-01T08:00:00+00:00", "2026-01-21T08:00:00+00:00"
    ) is None


def test_pair_latency_unparseable_is_none():
    assert compute_pair_latency_hours(None, "2026-01-01T08:00:00+00:00") is None
    assert compute_pair_latency_hours("not-a-date", "2026-01-01T08:00:00+00:00") is None


def test_insufficient_history_never_deviates():
    v = evaluate_latencies([10.0, 12.0])  # below the baseline+streak minimum
    assert v.deviated is False
    assert v.baseline_hours is None
    assert "insufficient" in v.explanation


def test_steady_replies_do_not_deviate():
    # Consistent ~12h replies — recent in line with baseline.
    v = evaluate_latencies([12.0, 10.0, 14.0, 11.0, 13.0, 12.0])
    assert v.deviated is False
    assert v.baseline_hours is not None


def test_sustained_slowdown_deviates():
    # Baseline ~12h, then three replies all far above (≥2x) — a pattern, not a fluke.
    v = evaluate_latencies([12.0, 10.0, 14.0, 48.0, 60.0, 72.0])
    assert v.deviated is True
    assert v.recent_hours == [48.0, 60.0, 72.0]
    assert "baseline" in v.explanation


def test_single_slow_reply_is_a_fluke_not_a_pattern():
    # One slow reply at the end, prior two recent are normal → streak not met.
    v = evaluate_latencies([12.0, 10.0, 14.0, 11.0, 13.0, 72.0])
    assert v.deviated is False


def test_two_slow_is_coincidence_not_yet_pattern():
    # Only the last two are slow; the third-from-last is normal → streak of 3 not met.
    v = evaluate_latencies([12.0, 10.0, 14.0, 11.0, 60.0, 72.0])
    assert v.deviated is False

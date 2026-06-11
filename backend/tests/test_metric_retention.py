"""Unit tests for the retention downsample planning (pure logic)."""

from services.metric_retention import plan_downsample_deletions


def _row(id, cust, metric, captured, stake=None):
    r = {"id": id, "customer": {"id": cust}, "metric": metric, "capturedAt": captured}
    if stake is not None:
        r["stakeholder"] = {"id": stake}
    return r


def test_no_duplicates_nothing_deleted():
    rows = [
        _row("a", "C1", "health_score", "2026-01-01T08:00:00+00:00"),
        _row("b", "C1", "health_score", "2026-01-02T08:00:00+00:00"),
    ]
    to_delete, kept = plan_downsample_deletions(rows)
    assert to_delete == [] and kept == 2  # different days → both kept


def test_same_day_keeps_latest_only():
    rows = [
        _row("a", "C1", "health_score", "2026-01-01T08:00:00+00:00"),
        _row("b", "C1", "health_score", "2026-01-01T20:00:00+00:00"),  # later same day
        _row("c", "C1", "health_score", "2026-01-01T12:00:00+00:00"),
    ]
    to_delete, kept = plan_downsample_deletions(rows)
    assert kept == 1
    assert set(to_delete) == {"a", "c"}  # 'b' (latest) survives


def test_stakeholder_rows_are_separated():
    # Two stakeholders, same customer/metric/day — each keeps its own row.
    rows = [
        _row("a", "C1", "response_latency", "2026-01-01T08:00:00+00:00", stake="S1"),
        _row("b", "C1", "response_latency", "2026-01-01T09:00:00+00:00", stake="S2"),
    ]
    to_delete, kept = plan_downsample_deletions(rows)
    assert to_delete == [] and kept == 2  # different stakeholders → not collapsed


def test_stakeholder_same_day_collapses_within_stakeholder():
    rows = [
        _row("a", "C1", "response_latency", "2026-01-01T08:00:00+00:00", stake="S1"),
        _row("b", "C1", "response_latency", "2026-01-01T18:00:00+00:00", stake="S1"),
        _row("c", "C1", "response_latency", "2026-01-01T09:00:00+00:00", stake="S2"),
    ]
    to_delete, kept = plan_downsample_deletions(rows)
    assert to_delete == ["a"] and kept == 2  # S1 keeps 'b', S2 keeps 'c'


def test_idempotent_on_already_daily_input():
    rows = [
        _row("a", "C1", "health_score", "2026-01-01T08:00:00+00:00"),
        _row("b", "C1", "engagement", "2026-01-01T08:00:00+00:00"),
    ]
    to_delete, _ = plan_downsample_deletions(rows)
    assert to_delete == []  # different metrics, one each → nothing to collapse

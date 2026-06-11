"""Unit tests for commitment follow-through reliability (pure compute)."""

from datetime import date

from services.commitment_reliability import compute_reliability

TODAY = date(2026, 6, 1)


def _c(side, status, due, delivered=None):
    return {"side": side, "status": status, "dueDate": due, "deliveredAt": delivered}


def test_no_due_dates_is_not_evaluable():
    commitments = [_c("us", "in_progress", None), _c("us", "done", None, "2026-05-01")]
    r = compute_reliability(commitments, "us", TODAY)
    assert r.reliability is None
    assert r.evaluated == 0


def test_delivered_on_time_counts():
    commitments = [_c("us", "done", "2026-05-20", "2026-05-18T10:00:00+00:00")]
    r = compute_reliability(commitments, "us", TODAY)
    assert r.evaluated == 1 and r.on_time == 1 and r.reliability == 1.0


def test_delivered_late_is_a_miss():
    commitments = [_c("us", "done", "2026-05-10", "2026-05-20T10:00:00+00:00")]
    r = compute_reliability(commitments, "us", TODAY)
    assert r.evaluated == 1 and r.on_time == 0 and r.reliability == 0.0


def test_past_due_undelivered_is_a_miss():
    commitments = [_c("them", "in_progress", "2026-05-15")]
    r = compute_reliability(commitments, "them", TODAY)
    assert r.evaluated == 1 and r.on_time == 0 and r.reliability == 0.0


def test_future_due_undelivered_not_yet_evaluable():
    commitments = [_c("us", "in_progress", "2026-06-30")]
    r = compute_reliability(commitments, "us", TODAY)
    assert r.reliability is None  # not due yet → not counted


def test_sides_are_separated():
    commitments = [
        _c("us", "done", "2026-05-10", "2026-05-09T00:00:00+00:00"),
        _c("them", "in_progress", "2026-05-01"),  # their miss
    ]
    assert compute_reliability(commitments, "us", TODAY).reliability == 1.0
    assert compute_reliability(commitments, "them", TODAY).reliability == 0.0

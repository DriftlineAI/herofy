"""Unit tests for milestone velocity + stakeholder-graph health (pure computes)."""

from datetime import date

from services.velocity_metrics import compute_milestone_velocity, compute_stakeholder_graph

TODAY = date(2026, 6, 1)


def _m(status, target):
    return {"status": status, "targetDate": target}


def test_velocity_none_without_dated_milestones():
    assert compute_milestone_velocity([_m("in_progress", None)], TODAY).score is None


def test_velocity_all_on_track():
    ms = [_m("in_progress", "2026-06-10"), _m("not_started", "2026-06-20")]
    r = compute_milestone_velocity(ms, TODAY)
    assert r.score == 1.0 and r.overdue == 0


def test_velocity_counts_overdue_and_days_behind():
    ms = [_m("in_progress", "2026-05-20"), _m("not_started", "2026-06-20")]
    r = compute_milestone_velocity(ms, TODAY)
    assert r.overdue == 1 and r.on_track == 1 and r.score == 0.5
    assert r.max_days_behind == 12


def test_velocity_done_milestones_ignored():
    ms = [_m("done", "2026-01-01"), _m("skipped", "2026-01-01"), _m("in_progress", "2026-06-30")]
    r = compute_milestone_velocity(ms, TODAY)
    assert r.score == 1.0 and r.on_track == 1  # only the open dated one counts


def test_graph_none_without_stakeholders():
    assert compute_stakeholder_graph([]).score is None


def test_graph_single_point_of_failure_no_champion():
    r = compute_stakeholder_graph([{"status": "active", "isChampion": False}])
    assert r.single_point_of_failure is True
    assert r.active_champions == 0
    assert r.score <= 0.5
    assert "single point of failure" in r.detail


def test_graph_multithreaded_with_champion_is_healthy():
    sts = [
        {"status": "active", "importance": "champion"},
        {"status": "active", "importance": "user"},
        {"status": "active", "importance": "technical"},
    ]
    r = compute_stakeholder_graph(sts)
    assert r.active_contacts == 3 and r.active_champions == 1
    assert r.score >= 0.9 and r.single_point_of_failure is False


def test_graph_departed_excluded():
    sts = [{"status": "departed", "isChampion": True}, {"status": "active", "isChampion": False}]
    r = compute_stakeholder_graph(sts)
    assert r.active_contacts == 1 and r.active_champions == 0

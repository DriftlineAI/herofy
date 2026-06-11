"""
Tests for metric_snapshots flag-gating, catalog discipline, and payload shape.

These exercise the deterministic write/read behavior with a fake DataConnect client
(no emulator needed): flag-off must be a true no-op, and a write must serialize the
inputs dict to JSON and pass the snapshot fields through unchanged.
"""

import json

import pytest

from services import metric_snapshots


class _FakeDC:
    def __init__(self):
        self.mutations: list[tuple[str, dict]] = []
        self.queries: list[tuple[str, dict]] = []

    async def execute_mutation(self, name, variables):
        self.mutations.append((name, variables))
        return {}

    async def execute_query(self, name, variables):
        self.queries.append((name, variables))
        return {"metricSnapshots": []}


class _Settings:
    def __init__(self, enabled):
        self.metric_snapshots_enabled = enabled


@pytest.fixture
def fake_dc(monkeypatch):
    dc = _FakeDC()
    monkeypatch.setattr(metric_snapshots, "get_dataconnect_client", lambda: dc)
    return dc


def _enable(monkeypatch, enabled):
    monkeypatch.setattr(metric_snapshots, "get_settings", lambda: _Settings(enabled))


@pytest.mark.asyncio
async def test_append_is_noop_when_flag_off(monkeypatch, fake_dc):
    _enable(monkeypatch, False)
    await metric_snapshots.append_snapshot(
        "ws", "cust", "health_score", value=72.0, trigger="sweep", inputs={"x": 1}
    )
    assert fake_dc.mutations == []  # no DB call at all


@pytest.mark.asyncio
async def test_append_writes_and_serializes_inputs(monkeypatch, fake_dc):
    _enable(monkeypatch, True)
    await metric_snapshots.append_snapshot(
        "ws", "cust", "health_score",
        value=72.0, state=None, prev_value=70.0, trigger="risk_signal",
        inputs={"reason": "champion silent", "contribs": {"a": -20}},
    )
    assert len(fake_dc.mutations) == 1
    name, v = fake_dc.mutations[0]
    assert name == "CreateMetricSnapshot"
    assert v["workspaceId"] == "ws" and v["customerId"] == "cust"
    assert v["metric"] == "health_score" and v["value"] == 72.0
    assert v["prevValue"] == 70.0 and v["trigger"] == "risk_signal"
    # inputs must be a JSON string round-trippable to the original dict
    assert json.loads(v["inputs"]) == {"reason": "champion silent", "contribs": {"a": -20}}


@pytest.mark.asyncio
async def test_unknown_metric_still_writes(monkeypatch, fake_dc):
    _enable(monkeypatch, True)
    # An off-catalog metric warns but is never silently dropped.
    await metric_snapshots.append_snapshot(
        "ws", "cust", "totally_new_metric", value=1.0, trigger="sweep", inputs={}
    )
    assert len(fake_dc.mutations) == 1


@pytest.mark.asyncio
async def test_get_latest_and_recent_noop_when_flag_off(monkeypatch, fake_dc):
    _enable(monkeypatch, False)
    assert await metric_snapshots.get_latest("ws", "cust", "health_score") is None
    assert await metric_snapshots.get_recent("ws", "cust", "health_score", "2026-01-01T00:00:00+00:00") == []
    assert fake_dc.queries == []  # no DB calls when off


@pytest.mark.asyncio
async def test_get_recent_passes_through_when_on(monkeypatch, fake_dc):
    _enable(monkeypatch, True)
    await metric_snapshots.get_recent("ws", "cust", "engagement_health", "2026-01-01T00:00:00+00:00")
    assert fake_dc.queries and fake_dc.queries[0][0] == "GetRecentMetricSnapshots"


def test_catalog_contains_all_heartbeat_metrics():
    # The metrics the heartbeat/inbound paths write must be in the known catalog.
    for m in (
        "health_score", "engagement", "sentiment", "engagement_health",
        "response_latency", "commitment_reliability_us", "commitment_reliability_them",
        "milestone_velocity", "stakeholder_graph",
    ):
        assert m in metric_snapshots.KNOWN_METRICS

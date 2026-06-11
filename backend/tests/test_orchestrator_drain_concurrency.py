"""
Tests for the Tier 1 concurrent drain — `orchestrator.queue.consumer.drain_workspace`.

`drain_workspace` runs a bounded `asyncio` pool of workers over a single shared
`repo.claim_next()`. These tests exercise the REAL pool + soft-cap logic but stub the
two collaborators so they run deterministically with no emulator and no LLM:

  - `_FakeRepo` hands out `n` distinct tasks and is collision-safe under concurrent
    `claim_next()` — it models the DB optimistic-claim "winner takes one" contract
    (the check-then-pop has no `await` between its steps, so it's atomic on the
    single-threaded event loop, exactly like the real CAS resolving to one winner).
  - `_Recorder` stands in for `_process_one`, recording peak simultaneous tasks and
    every task id it saw.

Guarantees covered: real parallelism (peak overlap == concurrency), exactly-once
processing (no dupes / no drops), full drain under the cap, sequential behavior at
concurrency=1 (legacy / rollback path), default concurrency sourced from settings,
and the `_MAX_TASKS_PER_DRAIN` soft cap.
"""

import asyncio

import pytest

import orchestrator.queue.consumer as consumer


class _FakeRepo:
    """Hands out `n` distinct tasks; concurrent claim_next() never returns a dupe."""

    def __init__(self, n: int):
        self._remaining = [{"id": f"task-{i}", "taskType": "demo"} for i in range(n)]

    async def claim_next(self):
        await asyncio.sleep(0)  # yield so pool workers interleave at the claim point
        # No await between the emptiness check and pop -> atomic on the event loop,
        # so two concurrent claimers can never receive the same task (the CAS contract).
        return self._remaining.pop(0) if self._remaining else None


class _Recorder:
    """Stand-in for `_process_one`: measures concurrency and records what it processed."""

    def __init__(self, work_sec: float = 0.03):
        self.work_sec = work_sec
        self.active = 0
        self.peak = 0
        self.seen: list[str] = []

    async def __call__(self, task, repo, workspace_id):
        self.active += 1
        self.peak = max(self.peak, self.active)
        self.seen.append(task["id"])
        await asyncio.sleep(self.work_sec)  # the "work" (stands in for run_worker)
        self.active -= 1


class _Settings:
    def __init__(self, concurrency: int):
        self.orchestration_drain_concurrency = concurrency


def _install(monkeypatch, n_tasks: int, work_sec: float = 0.03) -> _Recorder:
    """Wire a fresh fake repo + recording _process_one onto the real consumer module.

    drain_workspace builds the repo once and shares it across the pool, so we return the
    same instance for every AgentTaskRepository(...) call to model the shared queue.
    """
    repo = _FakeRepo(n_tasks)
    recorder = _Recorder(work_sec)
    monkeypatch.setattr(consumer, "AgentTaskRepository", lambda workspace_id: repo)
    monkeypatch.setattr(consumer, "_process_one", recorder)
    return recorder


@pytest.mark.asyncio
async def test_pool_runs_tasks_concurrently(monkeypatch):
    """A 10-wide pool processes 20 tasks with genuine overlap, each exactly once."""
    rec = _install(monkeypatch, n_tasks=20)

    processed = await consumer.drain_workspace("ws-test", concurrency=10)

    assert processed == 20
    assert rec.peak == 10                      # 10 genuinely in flight at once
    assert len(rec.seen) == 20                 # every task processed
    assert len(set(rec.seen)) == 20            # exactly once — no double-claim


@pytest.mark.asyncio
async def test_no_task_processed_twice_under_heavy_contention(monkeypatch):
    """Many workers racing a small queue still yields exactly-once, no drops."""
    rec = _install(monkeypatch, n_tasks=12, work_sec=0.01)

    processed = await consumer.drain_workspace("ws-test", concurrency=12)

    assert processed == 12
    assert len(rec.seen) == 12                                   # no drops
    assert set(rec.seen) == {f"task-{i}" for i in range(12)}     # all present, none dup'd


@pytest.mark.asyncio
async def test_concurrency_one_is_sequential(monkeypatch):
    """concurrency=1 reproduces the legacy serial drain — no overlap, FIFO order."""
    rec = _install(monkeypatch, n_tasks=8)

    processed = await consumer.drain_workspace("ws-test", concurrency=1)

    assert processed == 8
    assert rec.peak == 1                                   # never more than one in flight
    assert rec.seen == [f"task-{i}" for i in range(8)]     # strict FIFO, as before


@pytest.mark.asyncio
async def test_default_concurrency_comes_from_settings(monkeypatch):
    """Omitting the arg pulls the width from settings.orchestration_drain_concurrency."""
    rec = _install(monkeypatch, n_tasks=12)
    monkeypatch.setattr(consumer, "get_settings", lambda: _Settings(3))

    processed = await consumer.drain_workspace("ws-test")  # no concurrency arg

    assert processed == 12
    assert rec.peak == 3                       # honored the configured default


@pytest.mark.asyncio
async def test_empty_queue_is_a_noop(monkeypatch):
    """Nothing due -> zero processed, no work, no error."""
    rec = _install(monkeypatch, n_tasks=0)

    processed = await consumer.drain_workspace("ws-test", concurrency=10)

    assert processed == 0
    assert rec.seen == []


@pytest.mark.asyncio
async def test_soft_cap_bounds_a_single_drain(monkeypatch):
    """A single drain stops near _MAX_TASKS_PER_DRAIN even with more queued.

    The cap is a runaway-self-enqueue backstop, not an exact quota: workers re-check it
    before each claim, so up to `concurrency-1` extra tasks can slip past. We assert the
    documented window [cap, cap + concurrency - 1] and that the drain did NOT empty the
    (larger) queue.
    """
    cap = consumer._MAX_TASKS_PER_DRAIN
    n_tasks = cap + 20
    concurrency = 5
    rec = _install(monkeypatch, n_tasks=n_tasks, work_sec=0.005)

    processed = await consumer.drain_workspace("ws-test", concurrency=concurrency)

    assert cap <= processed <= cap + concurrency - 1   # soft cap honored
    assert processed < n_tasks                          # did not drain everything


@pytest.mark.asyncio
async def test_soft_cap_is_exact_when_sequential(monkeypatch):
    """At concurrency=1 the cap is exact — no slip, processes exactly _MAX_TASKS_PER_DRAIN."""
    cap = consumer._MAX_TASKS_PER_DRAIN
    rec = _install(monkeypatch, n_tasks=cap + 10, work_sec=0.001)

    processed = await consumer.drain_workspace("ws-test", concurrency=1)

    assert processed == cap

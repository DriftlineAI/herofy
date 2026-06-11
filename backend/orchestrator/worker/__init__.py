"""
The autonomous worker — the net-new agent.

`WorkerOutcome` is the consumer contract; `run_worker` (in agent.py) is the real
ADK `LlmAgent` + `PlanReActPlanner` implementation that investigates an account,
decides a response, dispatches plays as `AgentTool`s, records observations, and
self-enqueues follow-ups.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkerOutcome:
    """What the worker tells the consumer to do with the task."""

    status: str  # "done" | "waiting" | "failed"
    result: dict[str, Any] = field(default_factory=dict)
    blocking_need_id: str | None = None  # set when status == "waiting"
    clarifying_questions: list[dict] | None = None  # set when status == "waiting" (HITL form)
    error: str | None = None             # set when status == "failed"


# Imported after WorkerOutcome is defined (agent.py does `from . import WorkerOutcome`).
from .agent import run_worker  # noqa: E402

__all__ = ["WorkerOutcome", "run_worker"]

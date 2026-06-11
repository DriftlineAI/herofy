"""
Commitment follow-through reliability.

Trust is judged on follow-through: our reliability (side="us") is a leading trust
indicator; theirs (side="them") is a disengagement signal (docs/plans/SIGNAL_AGGREGATION.md).
A commitment is only measurable once it has a real dueDate — free-text dueLabel alone
can't be timed — so reliability is computed over commitments that carry a dueDate and
have come due. Result is persisted as a per-side MetricSnapshot.

compute_reliability() is pure (no DB). The heartbeat fetches commitments and snapshots
both sides.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass
class ReliabilityResult:
    """Follow-through reliability for one side over its evaluable commitments."""

    side: str                    # "us" | "them"
    evaluated: int               # commitments with a dueDate that have come due / been delivered
    on_time: int                 # delivered on or before the due date
    reliability: float | None    # on_time / evaluated, or None when nothing is evaluable yet
    detail: str


def _as_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        s = str(value)
        # Date scalar ("2026-06-01") or Timestamp ("2026-06-01T..."): take the date part.
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def compute_reliability(commitments: list[dict[str, Any]], side: str, today: date) -> ReliabilityResult:
    """Compute follow-through reliability for one side as of `today`.

    Evaluable = commitments for this side with a dueDate that have either been
    delivered or are already past due. On-time = delivered on/before the due date.
    A past-due, undelivered commitment counts as evaluated-but-missed.
    """
    evaluated = 0
    on_time = 0

    for c in commitments:
        if c.get("side") != side:
            continue
        due = _as_date(c.get("dueDate"))
        if due is None:
            continue  # not measurable without a real due date

        delivered_at = _as_date(c.get("deliveredAt"))
        is_done = c.get("status") == "done" or delivered_at is not None

        if is_done:
            evaluated += 1
            # On time when we know the delivery date and it's ≤ due; if delivered but
            # the timestamp is missing, give the benefit of the doubt (counts on-time).
            if delivered_at is None or delivered_at <= due:
                on_time += 1
        elif due < today:
            evaluated += 1  # past due and not delivered → a miss

    if evaluated == 0:
        return ReliabilityResult(side, 0, 0, None, "no due-dated commitments evaluable yet")

    reliability = round(on_time / evaluated, 3)
    detail = f"{on_time}/{evaluated} {side} commitments kept on time"
    return ReliabilityResult(side, evaluated, on_time, reliability, detail)

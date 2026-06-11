"""
Deterministic substrate metrics: milestone/onboarding velocity and stakeholder-graph
health (docs/plans/SIGNAL_AGGREGATION.md, Tier A/B with data already present).

Both are pure functions persisted as MetricSnapshots by the sweep heartbeat:
  - milestone_velocity: are onboarding/project milestones on track? (#1 leading
    indicator of early churn — days-behind / slippage).
  - stakeholder_graph: multi-threadedness, champion coverage, single-point-of-failure.

Recurring-issue detection and expansion-signal trajectory are intentionally NOT here —
they need issue-clustering / intent-extraction (an LLM/NLP track), tracked separately.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

_DONE_STATUSES = {"done", "skipped"}


def _as_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


@dataclass
class VelocityResult:
    score: float | None          # 0-1 on-track score (None = no dated milestones)
    on_track: int
    overdue: int
    max_days_behind: int
    detail: str


def compute_milestone_velocity(milestones: list[dict[str, Any]], today: date) -> VelocityResult:
    """On-track score over milestones that carry a target date.

    A dated, not-yet-done milestone past its target date is overdue; the score is the
    fraction of dated, still-open milestones that are NOT overdue. Completed milestones
    don't drag the score (they're done); undated ones aren't measurable.
    """
    open_dated = []
    for m in milestones:
        if m.get("status") in _DONE_STATUSES:
            continue
        due = _as_date(m.get("targetDate"))
        if due is not None:
            open_dated.append(due)

    if not open_dated:
        return VelocityResult(None, 0, 0, 0, "no dated open milestones")

    overdue_days = [(today - d).days for d in open_dated if d < today]
    overdue = len(overdue_days)
    on_track = len(open_dated) - overdue
    score = round(on_track / len(open_dated), 3)
    max_behind = max(overdue_days) if overdue_days else 0
    detail = (
        f"{on_track}/{len(open_dated)} milestones on track"
        + (f", worst {max_behind}d behind" if max_behind else "")
    )
    return VelocityResult(score, on_track, overdue, max_behind, detail)


@dataclass
class GraphHealthResult:
    score: float | None          # 0-1 (None = no stakeholders)
    active_contacts: int
    active_champions: int
    single_point_of_failure: bool
    detail: str


def compute_stakeholder_graph(stakeholders: list[dict[str, Any]]) -> GraphHealthResult:
    """Relationship breadth/resilience: multi-threadedness + champion coverage.

    Penalises single-point-of-failure (one active contact) and no-champion coverage.
    Importance falls back to isChampion when the structured tier is unset.
    """
    active = [s for s in stakeholders if (s.get("status") or "active") == "active"]
    if not active:
        return GraphHealthResult(None, 0, 0, False, "no stakeholders")

    def _is_champion(s) -> bool:
        return s.get("importance") == "champion" or bool(s.get("isChampion"))

    active_contacts = len(active)
    active_champions = sum(1 for s in active if _is_champion(s))
    spof = active_contacts == 1

    # Breadth: 1 contact → 0.3, 2 → 0.6, 3+ → 0.9 baseline.
    breadth_score = 0.3 if active_contacts == 1 else (0.6 if active_contacts == 2 else 0.9)
    # Champion coverage adds up to +0.1 (capped at 1.0); none caps the score lower.
    champion_bonus = 0.1 if active_champions >= 1 else 0.0
    score = round(min(1.0, breadth_score + champion_bonus), 3)
    if active_champions == 0:
        score = round(min(score, 0.5), 3)  # no champion is a real ceiling

    bits = [f"{active_contacts} active contact{'s' if active_contacts != 1 else ''}"]
    if active_champions == 0:
        bits.append("no champion")
    if spof:
        bits.append("single point of failure")
    return GraphHealthResult(score, active_contacts, active_champions, spof, "; ".join(bits))

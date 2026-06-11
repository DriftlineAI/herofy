"""
Signal Router

Decides whether a newly written Signal row warrants an orchestrator AgentTask,
then enqueues one if so. Called from both the reactive path (event_processor)
and the sweep path (signal_sweep_service).

Routing rules
─────────────
  going_dark  risk  → enqueue  priority 10
  going_dark  warn  → enqueue  priority 30
  cadence     risk  → enqueue  priority 15
  cadence     warn  → enqueue  priority 40
  sentiment   risk  → enqueue  priority 10
  sentiment   warn  → enqueue  priority 35
  engagement  risk  → enqueue  priority 15
  engagement  warn  → enqueue  priority 40
  commitments risk  → enqueue  priority 20
  commitments warn  → enqueue  priority 50
  *           ok    → skip

Dedup
─────
  If the customer already has an active (pending/in_progress/waiting) task,
  skip — the worker will pull all current signals when it runs.

  One exception: if the incoming signal is `risk` and the existing task has a
  lower-urgency priority (≥ 50), we lower its priority number so it gets
  processed sooner. This avoids re-enqueuing while still escalating.

Feature flag
────────────
  Does nothing (returns RouterResult(enqueued=False)) when
  settings.orchestration_enabled is False.
"""

from dataclasses import dataclass

from core.logging import get_logger
from db.dataconnect_client import get_dataconnect_client

logger = get_logger("SignalRouter")

# (kind, state) → priority. Missing entries mean "do not route".
_ROUTING_TABLE: dict[tuple[str, str], int] = {
    ("going_dark",  "risk"):  10,
    ("going_dark",  "warn"):  30,
    ("cadence",     "risk"):  15,
    ("cadence",     "warn"):  40,
    ("sentiment",   "risk"):  10,
    ("sentiment",   "warn"):  35,
    ("engagement",  "risk"):  15,
    ("engagement",  "warn"):  40,
    ("commitments", "risk"):  20,
    ("commitments", "warn"):  50,
}

# Existing task priority above this threshold is considered "low urgency" and
# eligible for escalation when a risk signal arrives.
_ESCALATION_THRESHOLD = 50


@dataclass
class RouterResult:
    enqueued: bool
    task_id: str | None = None
    skipped_reason: str | None = None  # 'flag_off' | 'no_route' | 'active_task'


async def route_signal(
    *,
    workspace_id: str,
    customer_id: str,
    signal_id: str,
    signal_kind: str,
    signal_state: str,
    signal_sentence: str = "",
) -> RouterResult:
    """
    Evaluate one signal and enqueue an AgentTask if warranted.

    Args:
        workspace_id:    Workspace UUID
        customer_id:     Customer UUID
        signal_id:       The Signal row just written (included in task payload)
        signal_kind:     'going_dark' | 'cadence' | 'sentiment' | 'engagement' | 'commitments'
        signal_state:    'ok' | 'warn' | 'risk'
        signal_sentence: Human-readable signal description (for task payload context)

    Returns:
        RouterResult describing what happened.
    """
    from config import get_settings
    settings = get_settings()
    if not settings.orchestration_enabled:
        return RouterResult(enqueued=False, skipped_reason="flag_off")

    priority = _ROUTING_TABLE.get((signal_kind, signal_state))
    if priority is None:
        logger.debug(
            "signal_not_routed",
            kind=signal_kind,
            state=signal_state,
            customer_id=customer_id,
        )
        return RouterResult(enqueued=False, skipped_reason="no_route")

    dc = get_dataconnect_client()

    # Check for an already-active task for this customer
    existing = await dc.execute_query(
        "GetActiveTasksForCustomer",
        {"workspaceId": workspace_id, "customerId": customer_id},
    )
    active_tasks = existing.get("agentTasks", [])

    if active_tasks:
        existing_task = active_tasks[0]
        existing_priority = existing_task.get("priority", 100)

        # Escalate: if this is a risk signal and the existing task is low-urgency,
        # lower its priority number so it gets claimed sooner.
        if signal_state == "risk" and existing_priority >= _ESCALATION_THRESHOLD:
            try:
                await dc.execute_mutation(
                    "EscalateAgentTaskPriority",
                    {
                        "id": existing_task["id"],
                        "priority": priority,
                    },
                )
                logger.info(
                    "signal_escalated_existing_task",
                    task_id=existing_task["id"],
                    old_priority=existing_priority,
                    new_priority=priority,
                    customer_id=customer_id,
                    signal_kind=signal_kind,
                )
            except Exception as e:
                # Non-fatal — escalation is best-effort
                logger.warning(
                    "signal_escalation_failed",
                    task_id=existing_task["id"],
                    error=str(e),
                )
        else:
            logger.debug(
                "signal_skipped_active_task",
                existing_task_id=existing_task["id"],
                existing_status=existing_task.get("status"),
                customer_id=customer_id,
            )

        return RouterResult(
            enqueued=False,
            task_id=existing_task["id"],
            skipped_reason="active_task",
        )

    # Enqueue a new task
    from orchestrator.queue.repository import AgentTaskRepository

    repo = AgentTaskRepository(workspace_id)
    task_id = await repo.enqueue(
        task_type="triage_signal",
        customer_id=customer_id,
        trigger_type="signal",
        payload={
            "signal_id": signal_id,
            "signal_kind": signal_kind,
            "signal_state": signal_state,
            "signal_sentence": signal_sentence,
            "source_event_id": signal_id,
        },
        priority=priority,
    )

    logger.info(
        "signal_routed_to_task",
        task_id=task_id,
        customer_id=customer_id,
        signal_kind=signal_kind,
        signal_state=signal_state,
        priority=priority,
    )
    return RouterResult(enqueued=True, task_id=task_id)

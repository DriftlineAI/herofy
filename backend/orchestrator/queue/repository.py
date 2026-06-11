"""
AgentTask queue repository.

Thin async wrapper over the DataConnect AgentTask operations. The spine of the
orchestrator: enqueue (incl. self-scheduled follow-ups via `scheduled_for`),
claim, pause/resume for durable HITL, and complete/fail.

Claim semantics: DataConnect has no `SELECT ... FOR UPDATE SKIP LOCKED`, so we
approximate it with a guarded optimistic compare-and-swap (`ClaimAgentTask`):
read the next due+pending task, then conditionally flip pending→in_progress and
treat affected-count==1 as a successful claim. Safe for a single worker and
collision-safe for a small pool (losers see count==0 and move on).
"""

import json
from datetime import datetime, timezone
from typing import Any

from core.logging import get_logger
from db.dataconnect_client import get_dataconnect_client

logger = get_logger("AgentTaskRepository")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _count(result: dict, op: str) -> int:
    """Pull the affected-row count out of an _updateMany/_deleteMany result."""
    node = result.get(op) or {}
    if isinstance(node, dict):
        return int(node.get("count", 0))
    if isinstance(node, int):
        return node
    return 0


class AgentTaskRepository:
    """CRUD + lifecycle for AgentTask rows, scoped to a workspace."""

    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id
        self.dc = get_dataconnect_client()

    # ------------------------------------------------------------------ enqueue
    async def enqueue(
        self,
        task_type: str,
        *,
        customer_id: str | None = None,
        trigger_type: str = "demo",
        payload: dict[str, Any] | None = None,
        priority: int = 100,
        scheduled_for: str | None = None,
    ) -> str:
        """Insert a pending task. `scheduled_for` (ISO) in the future enables
        self-scheduled follow-ups. Returns the new task id."""
        result = await self.dc.execute_mutation(
            "CreateAgentTask",
            {
                "workspaceId": self.workspace_id,
                "customerId": customer_id,
                "taskType": task_type,
                "triggerType": trigger_type,
                "payload": json.dumps(payload or {}),
                "priority": priority,
                "scheduledFor": scheduled_for or _now_iso(),
            },
        )
        task_id = (result.get("agentTask_insert") or {}).get("id")
        logger.info(
            "agent_task_enqueued",
            task_id=task_id,
            task_type=task_type,
            trigger_type=trigger_type,
            customer_id=customer_id,
            scheduled_for=scheduled_for,
        )
        return task_id

    # -------------------------------------------------------------------- claim
    async def get_next_pending(self) -> dict[str, Any] | None:
        """Return the next due+pending task (highest priority, oldest first)."""
        result = await self.dc.execute_query(
            "GetNextPendingAgentTask",
            {"workspaceId": self.workspace_id, "now": _now_iso()},
        )
        tasks = result.get("agentTasks", [])
        return tasks[0] if tasks else None

    async def claim(self, task_id: str) -> bool:
        """Guarded optimistic claim (pending→in_progress). True iff this caller won."""
        result = await self.dc.execute_mutation(
            "ClaimAgentTask",
            {"id": task_id, "now": _now_iso()},
        )
        won = _count(result, "agentTask_updateMany") == 1
        logger.info("agent_task_claim", task_id=task_id, won=won)
        return won

    async def claim_next(self) -> dict[str, Any] | None:
        """Atomic-ish 'get next + claim it'. Returns the claimed task or None.
        Retries the next candidate if it lost the claim race."""
        for _ in range(5):  # bounded retries to skip tasks lost to a racing worker
            task = await self.get_next_pending()
            if not task:
                return None
            if await self.claim(task["id"]):
                return task
        return None

    # ------------------------------------------------------------ link / status
    async def link_run(self, task_id: str, run_id: str) -> None:
        """Associate the AgentRun that's processing this task (progress streaming)."""
        await self.dc.execute_mutation(
            "UpdateAgentTaskStatus",
            {"id": task_id, "status": "in_progress", "agentRunId": run_id, "blockingNeedId": None},
        )

    async def pause(self, task_id: str, blocking_need_id: str) -> None:
        """Pause for HITL: in_progress→waiting + record the blocking need."""
        await self.dc.execute_mutation(
            "UpdateAgentTaskStatus",
            {"id": task_id, "status": "waiting", "agentRunId": None, "blockingNeedId": blocking_need_id},
        )
        logger.info("agent_task_paused", task_id=task_id, blocking_need_id=blocking_need_id)

    async def resume(self, task_id: str) -> None:
        """Resume after HITL answer: waiting→pending so a worker re-claims it."""
        await self.dc.execute_mutation(
            "UpdateAgentTaskStatus",
            {"id": task_id, "status": "pending", "agentRunId": None, "blockingNeedId": None},
        )
        logger.info("agent_task_resumed", task_id=task_id)

    async def resume_with_payload(self, task_id: str, payload: dict[str, Any]) -> None:
        """Resume with the human's answers merged into the payload (waiting→pending)."""
        await self.dc.execute_mutation(
            "ResumeAgentTaskWithAnswers",
            {"id": task_id, "payload": json.dumps(payload)},
        )
        logger.info("agent_task_resumed_with_answers", task_id=task_id)

    async def complete(self, task_id: str, result: dict[str, Any] | None = None) -> None:
        """Mark done with an optional JSON result."""
        await self.dc.execute_mutation(
            "CompleteAgentTask",
            {
                "id": task_id,
                "status": "done",
                "result": json.dumps(result) if result is not None else None,
                "errorMessage": None,
            },
        )
        logger.info("agent_task_completed", task_id=task_id)

    async def fail(self, task_id: str, error_message: str) -> None:
        """Mark failed with an error message."""
        await self.dc.execute_mutation(
            "CompleteAgentTask",
            {"id": task_id, "status": "failed", "result": None, "errorMessage": error_message[:2000]},
        )
        logger.warning("agent_task_failed", task_id=task_id, error=error_message[:200])

    async def get(self, task_id: str) -> dict[str, Any] | None:
        result = await self.dc.execute_query("GetAgentTask", {"id": task_id})
        return result.get("agentTask")

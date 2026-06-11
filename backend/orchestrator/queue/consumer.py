"""
Queue consumer — drains pending AgentTasks and invokes the worker.

Execution model (demo): kick-on-enqueue. `/demo-agent` enqueues then schedules a
drain; the consumer claims due tasks one at a time and runs them to completion.
No always-on poller (matches the "idle book = idle worker" cost model). Adding a
periodic poll loop later is a few lines (call `drain_workspace` on a timer).

Each task is wrapped in an AgentRun (reused tracking + Firestore streaming) so the
UI shows the worker reasoning. Durable HITL: a `waiting` outcome pauses the run and
marks the task `waiting` + `blockingNeedId`; the existing /answers flow resumes it.
"""

import asyncio
import time
from typing import Any

from config import get_settings
from core.logging import get_logger, bind_context, clear_context
from db.dataconnect_client import get_dataconnect_client
from services.agent_run_service import AgentRunService

from services.firestore_service import get_firestore_service
from ..runtime.callbacks import stream_status
from ..worker import run_worker, WorkerOutcome
from .repository import AgentTaskRepository

logger = get_logger("OrchestratorConsumer")

WORKER_AGENT_NAME = "orchestrator_worker"
_MAX_TASKS_PER_DRAIN = 25  # safety bound against runaway self-enqueue loops in one drain


async def sweep_due() -> dict:
    """Find every workspace with due+pending tasks and drain each. This is the periodic
    'production wake' entrypoint (Cloud Scheduler in prod, manual/dev otherwise) — it's
    what makes self-scheduled follow-ups and scheduled sweeps actually fire when due."""
    from datetime import datetime, timezone
    from db.dataconnect_client import get_dataconnect_client
    dc = get_dataconnect_client()
    res = await dc.execute_query("GetDuePendingTasks", {"now": datetime.now(timezone.utc).isoformat()})
    seen, ws_ids = set(), []
    for t in res.get("agentTasks", []):
        wid = (t.get("workspace") or {}).get("id")
        if wid and wid not in seen:
            seen.add(wid); ws_ids.append(wid)
    processed = {wid: await drain_workspace(wid) for wid in ws_ids}
    total = sum(processed.values())
    logger.info("orchestrator_sweep_complete", workspaces=len(ws_ids), processed=total)
    return {"workspaces": len(ws_ids), "processed_total": total, "per_workspace": processed}


async def drain_workspace(workspace_id: str, concurrency: int | None = None) -> int:
    """Claim and process due tasks for a workspace until the queue is empty.

    Runs up to `concurrency` tasks at once (default: settings.orchestration_drain_concurrency).
    `claim_next()`'s optimistic compare-and-swap guarantees no two pool members ever
    process the same task — losers of a claim race just move to the next candidate — so
    the pool needs no coordination beyond the shared repo. concurrency=1 reproduces the
    legacy sequential drain. Returns the number of tasks processed.

    The `_MAX_TASKS_PER_DRAIN` guard is a soft cap here: workers re-check it before each
    claim, so up to `concurrency-1` extra tasks can slip past it. That's fine — it's a
    runaway-self-enqueue backstop, not an exact quota."""
    if concurrency is None:
        concurrency = max(1, get_settings().orchestration_drain_concurrency)
    dc = get_dataconnect_client()
    repo = AgentTaskRepository(workspace_id)
    processed = 0

    async def pool_worker() -> None:
        nonlocal processed
        while processed < _MAX_TASKS_PER_DRAIN:
            task = await repo.claim_next()
            if not task:
                return  # nothing left due for this worker to claim
            processed += 1  # reserve the slot before the long-running task
            await _process_one(task, repo, workspace_id)

    # The worker/plays hit @check(auth.uid) ops on the admin surface; impersonate the workspace
    # owner so they pass (no request user here). NO_ACCESS queue ops stay pure-admin via the
    # client's per-op heuristic. gather() tasks inherit this context.
    async with dc.impersonate_workspace_owner(workspace_id):
        await asyncio.gather(*(pool_worker() for _ in range(concurrency)))
    logger.info("orchestrator_drain_complete", workspace_id=workspace_id,
                processed=processed, concurrency=concurrency)
    return processed


async def drain_workspace_detailed(workspace_id: str) -> list[dict[str, Any]]:
    """Like drain_workspace but returns per-task summaries for the pipeline test UI."""
    dc = get_dataconnect_client()
    repo = AgentTaskRepository(workspace_id)
    results: list[dict[str, Any]] = []
    # Impersonate the workspace owner so the plays' @check(auth.uid) ops pass on the admin surface.
    async with dc.impersonate_workspace_owner(workspace_id):
        while len(results) < _MAX_TASKS_PER_DRAIN:
            task = await repo.claim_next()
            if not task:
                break
            customer = task.get("customer") or {}
            t0 = time.monotonic()
            outcome = await _process_one_with_outcome(task, repo, workspace_id)
            duration_ms = int((time.monotonic() - t0) * 1000)
            results.append({
                "task_id": task["id"],
                "task_type": task.get("taskType", ""),
                "customer_name": customer.get("name", "unknown"),
                "status": outcome.get("status", "done"),
                "play": outcome.get("primary_play"),
                "duration_ms": duration_ms,
                "error": outcome.get("error"),
            })
    logger.info("orchestrator_drain_complete", workspace_id=workspace_id, processed=len(results))
    return results


async def _process_one_with_outcome(task: dict[str, Any], repo: AgentTaskRepository, workspace_id: str) -> dict[str, Any]:
    """Wrapper around _process_one that captures and returns the WorkerOutcome as a plain dict."""
    task_id = task["id"]
    customer = task.get("customer") or {}
    customer_id = customer.get("id")
    customer_name = customer.get("name")

    dc = get_dataconnect_client()
    run_service = AgentRunService(dc, workspace_id)

    run = await run_service.create_run(
        agent_name=WORKER_AGENT_NAME,
        trigger_type=task.get("triggerType", "demo"),
        triggered_by="orchestrator",
        input_params={"task_id": task_id, "customer_id": customer_id},
    )
    run_id = str(run["id"])

    bind_context(run_id=run_id, workspace_id=workspace_id, customer_id=customer_id, agent=WORKER_AGENT_NAME)

    from core.telemetry import task_trace
    async with task_trace(
        name=f"{task.get('taskType', 'task')}:{customer_name or customer_id or 'unknown'}",
        input={
            "task_type": task.get("taskType"),
            "trigger_type": task.get("triggerType"),
            "customer_name": customer_name,
        },
        metadata={
            "task_id": task_id,
            "run_id": run_id,
            "workspace_id": workspace_id,
        },
        session_id=workspace_id,   # groups all workspace tasks in Langfuse Sessions view
        user_id=customer_id,       # attributes cost/quality per customer
    ) as span:
        try:
            await repo.link_run(task_id, run_id)
            await run_service.start_run(run_id)
            await stream_status(run_id, "running", "claimed",
                                f"Picked up {task.get('taskType', 'task')}",
                                progress_pct=10, customer_id=customer_id, customer_name=customer_name)
            try:
                await get_firestore_service().set_active_run(workspace_id, run_id)
            except Exception:
                pass

            outcome: WorkerOutcome = await run_worker(task, run_id=run_id, workspace_id=workspace_id)

            if outcome.status == "waiting":
                await run_service.pause_run(run_id, pause_reason="Worker needs human input",
                                            clarifying_questions=outcome.clarifying_questions,
                                            blocking_need_id=outcome.blocking_need_id)
                await repo.pause(task_id, outcome.blocking_need_id)
                await stream_status(run_id, "waiting_for_input", "paused", "Waiting for your answer…",
                                    progress_pct=50, customer_id=customer_id, customer_name=customer_name)
                try:
                    await get_firestore_service().set_active_run(workspace_id, None)
                except Exception:
                    pass
                if span:
                    try:
                        span.update(output={"status": "waiting"}, level="DEFAULT")
                    except Exception:
                        pass
                return {"status": "waiting", "blocking_need_id": outcome.blocking_need_id}

            if outcome.status == "failed":
                await run_service.fail_run(run_id, outcome.error or "Worker failed")
                await repo.fail(task_id, outcome.error or "Worker failed")
                await stream_status(run_id, "failed", "error", outcome.error or "Worker failed",
                                    progress_pct=0, customer_id=customer_id, customer_name=customer_name)
                try:
                    await get_firestore_service().set_active_run(workspace_id, None)
                except Exception:
                    pass
                if span:
                    try:
                        span.update(output={"error": outcome.error}, level="ERROR")
                    except Exception:
                        pass
                return {"status": "failed", "error": outcome.error}

            await run_service.complete_run(run_id, result=outcome.result, customer_id=customer_id)
            await repo.complete(task_id, result=outcome.result)
            await stream_status(run_id, "completed", "done", "Task complete.",
                                progress_pct=100, customer_id=customer_id, customer_name=customer_name)
            try:
                await get_firestore_service().set_active_run(workspace_id, None)
            except Exception:
                pass
            if span:
                try:
                    span.update(output=outcome.result or {})
                except Exception:
                    pass
            return {"status": "done", **(outcome.result or {})}

        except Exception as e:
            logger.exception("task_processing_error", task_id=task_id, run_id=run_id, error=str(e))
            try:
                await run_service.fail_run(run_id, str(e))
                await repo.fail(task_id, str(e))
                await stream_status(run_id, "failed", "error", str(e),
                                    progress_pct=0, customer_id=customer_id, customer_name=customer_name)
                await get_firestore_service().set_active_run(workspace_id, None)
            except Exception:
                logger.exception("task_fail_cleanup_error", task_id=task_id)
            return {"status": "failed", "error": str(e)}
        finally:
            clear_context()


async def _process_one(task: dict[str, Any], repo: AgentTaskRepository, workspace_id: str) -> None:
    """Run a single claimed task inside an AgentRun, honoring the worker outcome."""
    task_id = task["id"]
    customer = task.get("customer") or {}
    customer_id = customer.get("id")
    customer_name = customer.get("name")

    dc = get_dataconnect_client()
    run_service = AgentRunService(dc, workspace_id)

    run = await run_service.create_run(
        agent_name=WORKER_AGENT_NAME,
        trigger_type=task.get("triggerType", "demo"),
        triggered_by="orchestrator",
        input_params={"task_id": task_id, "customer_id": customer_id},
    )
    run_id = str(run["id"])

    bind_context(run_id=run_id, workspace_id=workspace_id, customer_id=customer_id, agent=WORKER_AGENT_NAME)
    try:
        await repo.link_run(task_id, run_id)
        await run_service.start_run(run_id)
        await stream_status(
            run_id, "running", "claimed",
            f"Picked up {task.get('taskType', 'task')}",
            progress_pct=10, customer_id=customer_id, customer_name=customer_name,
        )
        try:
            await get_firestore_service().set_active_run(workspace_id, run_id)
        except Exception:
            pass

        outcome: WorkerOutcome = await run_worker(task, run_id=run_id, workspace_id=workspace_id)

        if outcome.status == "waiting":
            await run_service.pause_run(
                run_id,
                pause_reason="Worker needs human input",
                clarifying_questions=outcome.clarifying_questions,
                blocking_need_id=outcome.blocking_need_id,
            )
            await repo.pause(task_id, outcome.blocking_need_id)
            await stream_status(
                run_id, "waiting_for_input", "paused",
                "Waiting for your answer…",
                progress_pct=50, customer_id=customer_id, customer_name=customer_name,
            )
            try:
                await get_firestore_service().set_active_run(workspace_id, None)
            except Exception:
                pass
            logger.info("task_paused_for_hitl", task_id=task_id, run_id=run_id)
            return

        if outcome.status == "failed":
            await run_service.fail_run(run_id, outcome.error or "Worker failed")
            await repo.fail(task_id, outcome.error or "Worker failed")
            await stream_status(
                run_id, "failed", "error", outcome.error or "Worker failed",
                progress_pct=0, customer_id=customer_id, customer_name=customer_name,
            )
            try:
                await get_firestore_service().set_active_run(workspace_id, None)
            except Exception:
                pass
            return

        # done
        await run_service.complete_run(run_id, result=outcome.result, customer_id=customer_id)
        await repo.complete(task_id, result=outcome.result)
        await stream_status(
            run_id, "completed", "done", "Task complete.",
            progress_pct=100, customer_id=customer_id, customer_name=customer_name,
        )
        try:
            await get_firestore_service().set_active_run(workspace_id, None)
        except Exception:
            pass

    except Exception as e:  # never let one task kill the drain
        logger.exception("task_processing_error", task_id=task_id, run_id=run_id, error=str(e))
        try:
            await run_service.fail_run(run_id, str(e))
            await repo.fail(task_id, str(e))
            await stream_status(
                run_id, "failed", "error", str(e),
                progress_pct=0, customer_id=customer_id, customer_name=customer_name,
            )
            await get_firestore_service().set_active_run(workspace_id, None)
        except Exception:
            logger.exception("task_fail_cleanup_error", task_id=task_id)
    finally:
        clear_context()

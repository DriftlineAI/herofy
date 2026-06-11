"""
Agent Routes
FastAPI endpoints for triggering agents
"""

import asyncio
from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from middleware.auth import FirebaseUser, require_workspace_access, get_optional_user

# Lock to prevent concurrent answer submissions for the same run
# This prevents race conditions where double-clicks submit twice
_submit_locks: dict[str, asyncio.Lock] = {}
from core.types import (
    HandoffChainRequest,
    HandoffChainResponse,
    HandoffAutoRequest,
    HandoffAutoResponse,
    ResumeAgentRequest,
    AgentRunStatusResponse,
    AgentStatus,
)
from core.errors import HerofyError, AgentNotPausedError
from core.logging import get_logger
from agents.handoff_chain import run_handoff_chain
from agents.handoff_auto import (
    run_handoff_auto,
    resume_handoff_auto,
    check_and_resume_waiting_runs,
    handle_timed_out_runs,
)
from agents.signal_watcher_legacy import run_signal_watcher_chain
from agents.signal_watcher_unified import (
    run_signal_watcher_auto,
    resume_signal_watcher_auto,
)
from db.dataconnect_client import get_dataconnect_client
from services.agent_run_service import AgentRunService

router = APIRouter(prefix="/agents", tags=["agents"])
logger = get_logger("AgentRoutes")


@router.post("/handoff-chain/run", response_model=HandoffChainResponse)
async def trigger_handoff_chain(request: HandoffChainRequest) -> HandoffChainResponse:
    """
    Trigger the HandoffChain agent for a new deal.

    This endpoint is called by the Express API when a handoff is triggered
    from the frontend or detected by SignalWatcher.

    Args:
        request: HandoffChainRequest with workspace_id, notion_deal_id, optional customer_id

    Returns:
        HandoffChainResponse with run status and created record IDs
    """
    logger.info(
        "handoff_chain_triggered",
        workspace_id=request.workspace_id,
        notion_deal_id=request.notion_deal_id,
        customer_id=request.customer_id,
    )

    try:
        result = await run_handoff_chain(
            workspace_id=request.workspace_id,
            notion_deal_id=request.notion_deal_id,
            customer_id=request.customer_id,
        )

        return HandoffChainResponse(
            run_id=result.run_id,
            status=result.status,
            customer_id=result.customer_id,
            brief_id=result.brief_id,
            plan_id=result.plan_id,
            need_id=result.need_id,
            error=result.error,
        )

    except HerofyError as e:
        logger.error(
            "handoff_chain_error",
            error_code=e.code,
            error_message=e.message,
        )
        # Return error in Express format: {"error": {"message": ..., "code": ...}}
        return JSONResponse(
            status_code=500,
            content=e.to_dict(),
        )

    except Exception as e:
        logger.exception("handoff_chain_unexpected_error", error=str(e))
        # Return error in Express format
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": "Internal server error",
                    "code": "INTERNAL_ERROR",
                }
            },
        )


@router.get("/handoff-chain/status/{run_id}")
async def get_handoff_chain_status(run_id: str) -> dict:
    """
    Get the status of a HandoffChain run.

    Note: This is a placeholder. In a full implementation,
    we would store run status in a database or cache.
    """
    # TODO: Implement run status tracking
    return {
        "run_id": run_id,
        "status": "unknown",
        "message": "Run status tracking not yet implemented",
    }


# =============================================================================
# Handoff Auto (Autonomous Agent)
# =============================================================================


@router.post("/handoff-auto/run", response_model=HandoffAutoResponse)
async def trigger_handoff_auto(
    request: HandoffAutoRequest,
    background_tasks: BackgroundTasks,
) -> HandoffAutoResponse:
    """
    Trigger the autonomous HandoffAuto agent.

    This agent:
    - Runs in background (non-blocking)
    - Processes deals with confidence-aware decision making
    - Pauses for clarification when confidence is low
    - Resumes automatically when answers are provided

    Args:
        request: HandoffAutoRequest with workspace_id, optional notion_deal_id
        background_tasks: FastAPI background task manager

    Returns:
        HandoffAutoResponse with run_id immediately, agent runs in background
    """
    logger.info(
        "handoff_auto_triggered",
        workspace_id=request.workspace_id,
        customer_id=request.customer_id,
        notion_deal_id=request.notion_deal_id,
        trigger_type=request.trigger_type,
    )

    try:
        # Import here to avoid circular imports
        from db.dataconnect_client import get_dataconnect_client
        from services.agent_run_service import AgentRunService

        # Create the run record immediately
        dc = get_dataconnect_client()
        run_service = AgentRunService(dc, request.workspace_id)
        run = await run_service.create_run(
            agent_name="handoff_auto",
            trigger_type=request.trigger_type,
            triggered_by=None,
            input_params={
                "customer_id": request.customer_id,
                "notion_deal_id": request.notion_deal_id,
            },
        )
        run_id = run["id"]

        # Add to background tasks - runs after response is sent
        background_tasks.add_task(
            _run_handoff_auto_background,
            run_id=run_id,
            workspace_id=request.workspace_id,
            customer_id=request.customer_id,
            trigger_type=request.trigger_type,
        )

        # Return immediately with run_id
        return HandoffAutoResponse(
            run_id=run_id,
            status=AgentStatus.RUNNING,
            customer_id=request.customer_id,
        )

    except HerofyError as e:
        logger.error(
            "handoff_auto_error",
            error_code=e.code,
            error_message=e.message,
        )
        return JSONResponse(
            status_code=500,
            content=e.to_dict(),
        )

    except Exception as e:
        logger.exception("handoff_auto_unexpected_error", error=str(e))
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": "Internal server error",
                    "code": "INTERNAL_ERROR",
                }
            },
        )


@router.post("/handoff-auto/resume/{run_id}", response_model=HandoffAutoResponse)
async def resume_handoff_auto_run(
    run_id: str,
    request: ResumeAgentRequest,
) -> HandoffAutoResponse:
    """
    Resume a paused HandoffAuto agent run.

    Call this endpoint when a user has answered the clarifying questions.

    Args:
        run_id: The paused run UUID
        request: ResumeAgentRequest with answers

    Returns:
        HandoffAutoResponse with updated status
    """
    logger.info(
        "handoff_auto_resume",
        run_id=run_id,
        answer_count=len(request.answers),
    )

    try:
        result = await resume_handoff_auto(
            run_id=run_id,
            answers=request.answers,
        )

        return result

    except AgentNotPausedError as e:
        logger.warning("resume_not_paused", run_id=run_id)
        return JSONResponse(
            status_code=400,
            content=e.to_dict(),
        )

    except HerofyError as e:
        logger.error("resume_error", error_code=e.code)
        return JSONResponse(
            status_code=500,
            content=e.to_dict(),
        )

    except Exception as e:
        logger.exception("resume_unexpected_error", error=str(e))
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": "Internal server error",
                    "code": "INTERNAL_ERROR",
                }
            },
        )


async def _run_handoff_auto_background(
    run_id: str,
    workspace_id: str,
    customer_id: str | None,
    trigger_type: str,
) -> None:
    """
    Background task to run the autonomous handoff agent.

    This runs after the HTTP response is sent, so the UI is not blocked.
    """
    try:
        from agents.handoff_auto import run_handoff_auto

        result = await run_handoff_auto(
            workspace_id=workspace_id,
            customer_id=customer_id,
            trigger_type=trigger_type,
        )

        logger.info(
            "handoff_auto_background_complete",
            run_id=run_id,
            status=result.status.value if hasattr(result.status, 'value') else result.status,
            plan_id=result.plan_id,
            need_id=result.need_id,
        )

    except Exception as e:
        logger.exception(
            "handoff_auto_background_error",
            run_id=run_id,
            error=str(e),
        )


@router.get("/handoff-auto/status/{run_id}", response_model=AgentRunStatusResponse)
async def get_handoff_auto_status(run_id: str) -> AgentRunStatusResponse:
    """
    Get the current status of a HandoffAuto run.

    Args:
        run_id: The run UUID

    Returns:
        AgentRunStatusResponse with current state
    """
    dc = get_dataconnect_client()

    result = await dc.execute_query("GetAgentRunPublic", {"id": run_id})
    run = result.get("agentRun")

    if not run:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "message": "Run not found",
                    "code": "NOT_FOUND",
                }
            },
        )

    # Parse clarifying questions if present
    questions = None
    if run.get("clarifyingQuestions"):
        questions = run["clarifyingQuestions"]

    # Calculate progress
    step_order = [
        "read_deal", "read_playbook", "confidence_check",
        "gap_analysis", "write_handoff_brief", "generate_plan",
        "create_customer", "surface_need",
    ]
    current_step = run.get("currentStep")
    progress_pct = None
    if current_step and current_step in step_order:
        progress_pct = int((step_order.index(current_step) + 1) / len(step_order) * 100)

    # Extract nested object IDs
    customer = run.get("customer")
    brief = run.get("brief")
    plan = run.get("plan")

    return AgentRunStatusResponse(
        run_id=run_id,
        status=AgentStatus(run["status"]),
        current_step=current_step,
        paused_at=run.get("pausedAt"),
        questions=questions,
        progress_pct=progress_pct,
        customer_id=str(customer["id"]) if customer else None,
        brief_id=str(brief["id"]) if brief else None,
        plan_id=str(plan["id"]) if plan else None,
    )


@router.post("/handoff-auto/poll/{workspace_id}")
async def trigger_poll(
    workspace_id: str,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    DEPRECATED: Use /sync/poll?integration=notion&workspace_id=... instead.

    Polling is now handled by SyncOrchestrator which routes through
    SignalWatcherEventProcessor for proper customer creation.
    """
    from fastapi import HTTPException

    raise HTTPException(
        status_code=410,  # Gone
        detail="This endpoint is deprecated. Use POST /sync/notion/sync?workspace_id=... instead.",
    )


@router.get("/handoff-auto/runs/{workspace_id}")
async def list_agent_runs(
    workspace_id: str,
    status: str | None = None,
    limit: int = 50,
) -> dict:
    """
    List agent runs for a workspace.

    Args:
        workspace_id: The workspace UUID
        status: Optional filter by status
        limit: Max records to return

    Returns:
        List of agent runs
    """
    dc = get_dataconnect_client()

    result = await dc.execute_query(
        "ListAgentRunsForWorkspace",
        {
            "workspaceId": workspace_id,
            "agentName": "handoff_auto",
            "status": status,
            "limit": limit,
        },
    )

    runs = result.get("agentRuns", [])

    # Transform nested objects to match legacy format
    for run in runs:
        customer = run.pop("customer", None)
        brief = run.pop("brief", None)
        plan = run.pop("plan", None)

        run["customerId"] = customer["id"] if customer else None
        run["briefId"] = brief["id"] if brief else None
        run["planId"] = plan["id"] if plan else None

    return {
        "runs": runs,
        "count": len(runs),
    }


# =============================================================================
# Workspace-Scoped Agent Run Endpoints (for Frontend HITL UI)
# =============================================================================

# Separate router for workspace-scoped endpoints
workspace_agents_router = APIRouter(prefix="/workspaces", tags=["workspace-agents"])


class SubmitAnswersRequest(BaseModel):
    """Request body for submitting answers to agent questions."""
    answers: list[dict]  # List of {"question_id": str, "answer": str}


@workspace_agents_router.get("/{workspace_id}/agent-runs/{run_id}")
async def get_agent_run_detail(
    workspace_id: str,
    run_id: str,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> dict:
    """
    Get detailed agent run information including questions for the HITL UI.

    Returns full run details with questions formatted for the frontend.
    """
    dc = get_dataconnect_client()

    # Fetch the agent run
    result = await dc.execute_query("GetAgentRun", {"id": run_id})
    run = result.get("agentRun")

    if not run:
        return JSONResponse(
            status_code=404,
            content={"error": {"message": "Agent run not found", "code": "NOT_FOUND"}},
        )

    # Extract nested objects
    customer = run.get("customer")
    blocking_need = run.get("blockingNeed")

    # Format questions
    questions = run.get("clarifyingQuestions") or []

    return {
        "run": {
            "id": str(run["id"]),
            "workspace_id": workspace_id,
            "agent_name": run["agentName"],
            "trigger_source": run.get("triggerType", "manual"),
            "status": run["status"],
            "current_step": run.get("currentStep"),
            "confidence_level": run.get("confidenceLevel"),
            "paused_at_step": run.get("pausedAtStep"),  # Note: This field doesn't exist in schema
            "paused_at": run["pausedAt"] if run.get("pausedAt") else None,
            "questions": questions,
            "customer_id": str(customer["id"]) if customer else None,
            "customer_name": customer.get("name") if customer else None,
            "error_message": run.get("errorMessage"),
            "started_at": run["startedAt"] if run.get("startedAt") else None,
            "completed_at": run["completedAt"] if run.get("completedAt") else None,
        },
        "need": blocking_need,
        "customer_name": customer.get("name") if customer else None,
    }


@workspace_agents_router.get("/{workspace_id}/agent-runs")
async def list_workspace_agent_runs(
    workspace_id: str,
    status: str | None = None,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> dict:
    """
    List agent runs for a workspace, optionally filtered by status.

    Used by frontend to show waiting runs in the Today queue.
    """
    dc = get_dataconnect_client()

    result = await dc.execute_query(
        "ListAgentRunsForWorkspace",
        {
            "workspaceId": workspace_id,
            "agentName": None,  # No filter on agentName
            "status": status,
            "limit": 50,
        },
    )

    runs = result.get("agentRuns", [])

    # Format runs for frontend
    formatted_runs = []
    for run in runs:
        customer = run.get("customer")
        formatted_runs.append({
            "id": str(run["id"]),
            "agent_name": run["agentName"],
            "status": run["status"],
            "trigger_source": run.get("triggerType"),
            "current_step": run.get("currentStep"),
            "paused_at": run["pausedAt"] if run.get("pausedAt") else None,
            "started_at": run["startedAt"] if run.get("startedAt") else None,
            "customer_id": str(customer["id"]) if customer else None,
            "customer_name": customer.get("name") if customer else None,
            "questions": run.get("clarifyingQuestions") or [],
        })

    return {"runs": formatted_runs}


@workspace_agents_router.post("/{workspace_id}/agent-runs/{run_id}/answers")
async def submit_agent_answers(
    workspace_id: str,
    run_id: str,
    request: SubmitAnswersRequest,
    background_tasks: BackgroundTasks,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> dict:
    """
    Submit answers to agent questions and resume the agent.

    This is the main HITL endpoint - user answers questions,
    agent resumes with the clarified information.

    Answers are persisted to agent_run_answers table for audit and resume.
    """
    logger.info(
        "submit_agent_answers",
        workspace_id=workspace_id,
        run_id=run_id,
        answer_count=len(request.answers),
        user_id=user.uid,
    )

    # Acquire lock to prevent concurrent submissions for the same run.
    # Clean up the entry after release so the dict doesn't grow unbounded.
    lock = _submit_locks.setdefault(run_id, asyncio.Lock())
    try:
        async with lock:
            try:
                # Verify run exists and is waiting using DataConnect
                from db.dataconnect_client import get_dataconnect_client
                dc = get_dataconnect_client()
                run = await dc.get_agent_run(run_id)

                if not run:
                    return JSONResponse(
                        status_code=404,
                        content={"error": {"message": "Agent run not found", "code": "NOT_FOUND"}},
                    )

                # Verify workspace matches. Normalize both (UUIDs come back dashless from Data
                # Connect, but the URL workspace_id can be dashed) — a raw compare 404s across formats.
                from tools.database_tool import normalize_uuid
                run_ws = run.get("workspace", {}).get("id")
                if not run_ws or normalize_uuid(run_ws) != normalize_uuid(workspace_id):
                    return JSONResponse(
                        status_code=404,
                        content={"error": {"message": "Agent run not found", "code": "NOT_FOUND"}},
                    )

                # running/completed → already done; safe to return success without re-dispatching.
                if run["status"] in ("running", "completed"):
                    logger.info(
                        "submit_answers_idempotent",
                        run_id=run_id,
                        status=run["status"],
                        message="Agent already processing or completed - returning success",
                    )
                    return {
                        "status": "ok",
                        "message": f"Agent already {run['status']}",
                        "idempotent": True,
                    }

                # 'resuming' is RESUMABLE, not idempotent: a run can get stuck here if a prior resume
                # never actually dispatched (e.g. the old frontend pre-set status, or a dropped task).
                # Re-running the resume is safe — the AgentTask claim de-dups and the demo send action
                # is idempotent — and it's the only path that resolves the blocking Need.
                if run["status"] not in ("waiting_for_input", "resuming"):
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": {
                                "message": f"Agent run is not waiting for input (status: {run['status']})",
                                "code": "AGENT_NOT_PAUSED",
                            }
                        },
                    )

                # Convert answers to the format expected by resume
                answers_dict = {a["question_id"]: a["answer"] for a in request.answers}

                # Flip status to resuming in the DB *before* releasing the lock so that any
                # concurrent request that queued behind this one sees "resuming" and short-circuits.
                await dc.resume_agent_run(run_id, answers_dict)

                # Resolve the blocking Need so it disappears from Today queue
                blocking_need = run.get("blockingNeed")
                if blocking_need and blocking_need.get("id"):
                    try:
                        await dc.execute_mutation("ResolveNeed", {"id": blocking_need["id"]})
                        logger.info(
                            "blocking_need_resolved",
                            need_id=blocking_need["id"],
                            run_id=run_id,
                        )

                        # Push real-time notification to refresh Today queue
                        try:
                            from services.firestore_service import get_firestore_service

                            firestore = get_firestore_service()
                            await firestore.notify_need_resolved(
                                workspace_id=workspace_id,
                                need_id=blocking_need["id"],
                            )
                        except Exception as fs_error:
                            logger.warning(
                                "need_resolved_notification_failed",
                                need_id=blocking_need["id"],
                                error=str(fs_error),
                            )
                    except Exception as e:
                        # Non-fatal - log and continue
                        logger.warning(
                            "blocking_need_resolution_failed",
                            need_id=blocking_need.get("id"),
                            error=str(e),
                        )

                # Auto-resolve any SidekickItems linked to this AgentRun
                # This keeps the nav badge count in sync and clears items from RightRail
                try:
                    from services.sidekick_service import SidekickService
                    sidekick = SidekickService(dc, workspace_id)
                    resolved_items = await sidekick.auto_resolve_for_agent_run(
                        agent_run_id=run_id,
                        resolved_by_user_id=user.uid,
                    )
                    if resolved_items:
                        logger.info(
                            "sidekick_items_auto_resolved",
                            run_id=run_id,
                            resolved_count=len(resolved_items),
                        )
                except Exception as e:
                    # Non-fatal - log and continue
                    logger.warning(
                        "sidekick_auto_resolve_failed",
                        run_id=run_id,
                        error=str(e),
                    )

                # Resume the agent in background. Orchestrator worker runs resume via the
                # queue (flip the blocked AgentTask to pending + drain); everything else
                # uses the existing handoff_auto resume. This branch only triggers for
                # runs the orchestrator created, so handoff_auto is unaffected.
                if run.get("agentName") == "orchestrator_worker" and blocking_need and blocking_need.get("id"):
                    try:
                        from routes.orchestrator import resume_orchestrator_run
                        background_tasks.add_task(
                            resume_orchestrator_run, workspace_id, blocking_need["id"], answers_dict
                        )
                    except Exception as e:
                        logger.warning("orchestrator_resume_dispatch_failed", run_id=run_id, error=str(e))
                else:
                    background_tasks.add_task(
                        _resume_agent_background,
                        run_id,
                        answers_dict,
                    )

                return {
                    "run": {
                        "id": run_id,
                        "status": "resuming",
                    },
                    "message": "Answers submitted. Agent is resuming.",
                }

            except Exception as e:
                logger.exception("submit_answers_error", run_id=run_id, error=str(e))
                return JSONResponse(
                    status_code=500,
                    content={"error": {"message": str(e), "code": "INTERNAL_ERROR"}},
                )
    finally:
        _submit_locks.pop(run_id, None)


async def _resume_agent_background(run_id: str, answers: dict):
    """Background task to resume an agent after answers are submitted.

    If the agent fails during resume, we:
    1. Mark the agent run as failed
    2. Log the error for debugging

    Note: The blocking Need is already resolved when answers are submitted.
    If the agent fails, a new run should be created rather than reopening
    the old Need - this keeps the audit trail clean.
    """
    from db.dataconnect_client import get_dataconnect_client

    try:
        result = await resume_handoff_auto(run_id=run_id, answers=answers)
        logger.info(
            "agent_resumed",
            run_id=run_id,
            result_status=result.status,
        )
    except Exception as e:
        logger.exception("agent_resume_background_error", run_id=run_id, error=str(e))

        # Mark the agent run as failed so it doesn't stay in "resuming" limbo
        try:
            dc = get_dataconnect_client()
            await dc.execute_mutation(
                "FailAgentRun",
                {
                    "id": run_id,
                    "errorMessage": f"Agent failed during resume: {str(e)[:500]}",
                },
            )
            logger.info("agent_run_marked_failed", run_id=run_id)
        except Exception as fail_err:
            logger.error(
                "failed_to_mark_agent_run_failed",
                run_id=run_id,
                error=str(fail_err),
            )


@workspace_agents_router.post("/{workspace_id}/agent-runs/{run_id}/skip")
async def skip_agent_questions(
    workspace_id: str,
    run_id: str,
    background_tasks: BackgroundTasks,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> dict:
    """
    Skip agent questions and continue in draft mode.

    When user doesn't want to answer questions, the agent
    continues with lower confidence and outputs a draft
    for human review.
    """
    logger.info("skip_agent_questions", workspace_id=workspace_id, run_id=run_id)

    try:
        from db.dataconnect_client import get_dataconnect_client
        dc = get_dataconnect_client()
        run = await dc.get_agent_run(run_id)

        if not run:
            return JSONResponse(
                status_code=404,
                content={"error": {"message": "Agent run not found", "code": "NOT_FOUND"}},
            )

        # Verify workspace matches
        if run.get("workspace", {}).get("id") != workspace_id:
            return JSONResponse(
                status_code=404,
                content={"error": {"message": "Agent run not found", "code": "NOT_FOUND"}},
            )

        # Accept both waiting_for_input and resuming (frontend may have already updated status)
        if run["status"] not in ("waiting_for_input", "resuming"):
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "message": f"Agent run is not waiting for input",
                        "code": "AGENT_NOT_PAUSED",
                    }
                },
            )

        # Resume with empty answers (triggers draft mode)
        background_tasks.add_task(
            _resume_agent_background,
            run_id,
            {},  # Empty answers triggers draft mode
        )

        return {
            "run": {
                "id": run_id,
                "status": "resuming",
            },
            "message": "Questions skipped. Agent continuing in draft mode.",
        }

    except Exception as e:
        logger.exception("skip_questions_error", run_id=run_id, error=str(e))
        return JSONResponse(
            status_code=500,
            content={"error": {"message": str(e), "code": "INTERNAL_ERROR"}},
        )


# =============================================================================
# SignalWatcher Chain Agent
# =============================================================================


class SignalWatcherChainRequest(BaseModel):
    """Request body for SignalWatcher chain agent."""
    workspace_id: str


class SignalWatcherChainResponse(BaseModel):
    """Response from SignalWatcher chain agent."""
    run_id: str
    status: str
    signals_processed: int = 0
    needs_created: int = 0
    threads_created: int = 0
    interactions_created: int = 0
    stakeholders_updated: int = 0
    error: str | None = None
    duration_ms: int | None = None


@router.post("/signal-watcher-chain/run", response_model=SignalWatcherChainResponse)
async def trigger_signal_watcher_chain(
    request: SignalWatcherChainRequest,
) -> SignalWatcherChainResponse:
    """
    Trigger the SignalWatcher chain agent to process incoming signals.

    This is the sequential (deterministic) version that processes all
    signals without pause/resume capability.

    Args:
        request: SignalWatcherChainRequest with workspace_id

    Returns:
        SignalWatcherChainResponse with processing results
    """
    logger.info(
        "signal_watcher_chain_triggered",
        workspace_id=request.workspace_id,
    )

    try:
        result = await run_signal_watcher_chain(
            workspace_id=request.workspace_id,
        )

        return SignalWatcherChainResponse(
            run_id=result.run_id,
            status=result.status,
            signals_processed=result.signals_processed,
            needs_created=result.needs_created,
            threads_created=result.threads_created,
            interactions_created=result.interactions_created,
            stakeholders_updated=result.stakeholders_updated,
            error=result.error,
            duration_ms=result.duration_ms,
        )

    except HerofyError as e:
        logger.error(
            "signal_watcher_chain_error",
            error_code=e.code,
            error_message=e.message,
        )
        return JSONResponse(
            status_code=500,
            content=e.to_dict(),
        )

    except Exception as e:
        logger.exception("signal_watcher_chain_unexpected_error", error=str(e))
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": "Internal server error",
                    "code": "INTERNAL_ERROR",
                }
            },
        )


# =============================================================================
# SignalWatcher Auto Agent (Autonomous with Pause/Resume)
# =============================================================================


class SignalWatcherAutoRequest(BaseModel):
    """Request body for SignalWatcher auto agent."""
    workspace_id: str
    trigger_type: str = "manual"
    settings_override: dict | None = None


class SignalWatcherAutoResponse(BaseModel):
    """Response from SignalWatcher auto agent."""
    run_id: str
    status: str
    signals_processed: int = 0
    needs_created: int = 0
    threads_created: int = 0
    interactions_created: int = 0
    stakeholders_updated: int = 0
    need_id: str | None = None  # If paused, the need to answer
    questions: list[dict] | None = None  # If paused, the questions
    error: str | None = None


@router.post("/signal-watcher-auto/run", response_model=SignalWatcherAutoResponse)
async def trigger_signal_watcher_auto(
    request: SignalWatcherAutoRequest,
) -> SignalWatcherAutoResponse:
    """
    Trigger the autonomous SignalWatcher agent.

    This agent:
    - Processes signals with confidence-aware decision making
    - Pauses for clarification when confidence is low
    - Resumes automatically when answers are provided

    Args:
        request: SignalWatcherAutoRequest with workspace_id and options

    Returns:
        SignalWatcherAutoResponse with status and any pause information
    """
    logger.info(
        "signal_watcher_auto_triggered",
        workspace_id=request.workspace_id,
        trigger_type=request.trigger_type,
    )

    try:
        result = await run_signal_watcher_auto(
            workspace_id=request.workspace_id,
            trigger_type=request.trigger_type,
            settings_override=request.settings_override,
        )

        return SignalWatcherAutoResponse(
            run_id=result.run_id,
            status=result.status,
            signals_processed=result.signals_processed,
            needs_created=result.needs_created,
            threads_created=result.threads_created,
            interactions_created=result.interactions_created,
            stakeholders_updated=result.stakeholders_updated,
            need_id=result.need_id,
            questions=result.questions,
            error=result.error,
        )

    except HerofyError as e:
        logger.error(
            "signal_watcher_auto_error",
            error_code=e.code,
            error_message=e.message,
        )
        return JSONResponse(
            status_code=500,
            content=e.to_dict(),
        )

    except Exception as e:
        logger.exception("signal_watcher_auto_unexpected_error", error=str(e))
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": "Internal server error",
                    "code": "INTERNAL_ERROR",
                }
            },
        )


@router.post("/signal-watcher-auto/resume/{run_id}", response_model=SignalWatcherAutoResponse)
async def resume_signal_watcher_auto_run(
    run_id: str,
    request: ResumeAgentRequest,
) -> SignalWatcherAutoResponse:
    """
    Resume a paused SignalWatcher auto agent run.

    Call this endpoint when a user has answered the clarifying questions.

    Args:
        run_id: The paused run UUID
        request: ResumeAgentRequest with answers

    Returns:
        SignalWatcherAutoResponse with updated status
    """
    logger.info(
        "signal_watcher_auto_resume",
        run_id=run_id,
        answer_count=len(request.answers),
    )

    try:
        # Get workspace_id from the run record
        dc = get_dataconnect_client()
        result_data = await dc.execute_query("GetAgentRunWorkspace", {"id": run_id})
        run = result_data.get("agentRun")

        if not run:
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "message": "Run not found",
                        "code": "NOT_FOUND",
                    }
                },
            )

        workspace = run.get("workspace")
        workspace_id = workspace["id"] if workspace else None

        result = await resume_signal_watcher_auto(
            workspace_id=workspace_id,
            run_id=run_id,
            answers=request.answers,
        )

        return SignalWatcherAutoResponse(
            run_id=result.run_id,
            status=result.status,
            signals_processed=result.signals_processed,
            needs_created=result.needs_created,
            threads_created=result.threads_created,
            interactions_created=result.interactions_created,
            stakeholders_updated=result.stakeholders_updated,
            need_id=result.need_id,
            questions=result.questions,
            error=result.error,
        )

    except AgentNotPausedError as e:
        logger.warning("signal_watcher_resume_not_paused", run_id=run_id)
        return JSONResponse(
            status_code=400,
            content=e.to_dict(),
        )

    except HerofyError as e:
        logger.error("signal_watcher_resume_error", error_code=e.code)
        return JSONResponse(
            status_code=500,
            content=e.to_dict(),
        )

    except Exception as e:
        logger.exception("signal_watcher_resume_unexpected_error", error=str(e))
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": "Internal server error",
                    "code": "INTERNAL_ERROR",
                }
            },
        )


@router.get("/signal-watcher-auto/status/{run_id}")
async def get_signal_watcher_status(run_id: str) -> dict:
    """
    Get the current status of a SignalWatcher auto run.

    Args:
        run_id: The run UUID

    Returns:
        Status information including progress and any questions
    """
    dc = get_dataconnect_client()

    result = await dc.execute_query("GetAgentRunPublic", {"id": run_id})
    run = result.get("agentRun")

    if not run:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "message": "Run not found",
                    "code": "NOT_FOUND",
                }
            },
        )

    # Calculate progress
    step_order = [
        "fetch_signals", "classify_signals", "match_threads",
        "match_needs", "confidence_check", "extract_profiles",
        "create_interactions", "update_watermarks",
    ]
    current_step = run.get("currentStep")
    progress_pct = None
    if current_step and current_step in step_order:
        progress_pct = int((step_order.index(current_step) + 1) / len(step_order) * 100)

    return {
        "run_id": run_id,
        "status": run["status"],
        "current_step": current_step,
        "progress_pct": progress_pct,
        "paused_at": run["pausedAt"] if run.get("pausedAt") else None,
        "questions": run.get("clarifyingQuestions"),
        "result": run.get("result"),
        "error": run.get("errorMessage"),
    }


@router.post("/signal-watcher-auto/poll/{workspace_id}")
async def trigger_signal_watcher_poll(
    workspace_id: str,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    Manually trigger signal watching for a workspace.

    This can also be called by a scheduler (e.g., Cloud Scheduler, cron).

    Args:
        workspace_id: The workspace UUID
        background_tasks: FastAPI background tasks

    Returns:
        Acknowledgment that polling was triggered
    """
    logger.info("signal_watcher_poll_triggered", workspace_id=workspace_id)

    # Run in background
    background_tasks.add_task(_signal_watcher_poll_background, workspace_id)

    return {
        "status": "polling_started",
        "workspace_id": workspace_id,
    }


async def _signal_watcher_poll_background(workspace_id: str):
    """Background task for signal watcher polling."""
    try:
        result = await run_signal_watcher_auto(
            workspace_id=workspace_id,
            trigger_type="scheduled",
            triggered_by="poll_endpoint",
        )
        logger.info(
            "signal_watcher_poll_complete",
            workspace_id=workspace_id,
            status=result.status,
            signals_processed=result.signals_processed,
        )
    except Exception as e:
        logger.exception(
            "signal_watcher_poll_error",
            workspace_id=workspace_id,
            error=str(e),
        )


# =============================================================================
# Recovery: Stuck Needs
# =============================================================================


class RecoverStuckNeedsResponse(BaseModel):
    """Response from recovering stuck needs."""
    recovered: int
    failed: int
    details: list[dict]
    debug: list[dict] = []  # Debug info about all needs checked


@workspace_agents_router.post("/{workspace_id}/recover-stuck-needs")
async def recover_stuck_needs(
    workspace_id: str,
    background_tasks: BackgroundTasks,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> RecoverStuckNeedsResponse:
    """
    Find and recover stuck sidekick_question needs.

    A need is "stuck" if:
    - It's of type sidekick_question and unresolved
    - Its linked agent run has no clarifying questions OR is stuck in 'running'

    Recovery:
    - Fails the old stuck agent run (if any)
    - Triggers a new handoff_auto run for the customer
    - The new run will generate questions for the need

    This can be called manually or by a scheduled job.
    """
    from db.dataconnect_client import get_dataconnect_client

    logger.info("recover_stuck_needs_started", workspace_id=workspace_id)

    dc = get_dataconnect_client()

    # Get all sidekick_question needs
    result = await dc.execute_query(
        "GetSidekickQuestionNeeds",
        {"workspaceId": workspace_id},
    )
    needs = result.get("needs", [])

    # Find stuck needs (no questions or agent run stuck in 'running')
    stuck_needs = []
    debug_info = []

    for need in needs:
        agent_run = need.get("agentRun")
        has_questions = False
        question_count = 0

        if agent_run and agent_run.get("clarifyingQuestions"):
            try:
                import json
                parsed = json.loads(agent_run["clarifyingQuestions"])
                has_questions = isinstance(parsed, list) and len(parsed) > 0
                question_count = len(parsed) if has_questions else 0
            except:
                has_questions = False

        # Collect debug info for every need
        debug_info.append({
            "need_id": need["id"],
            "customer_name": need.get("customer", {}).get("name"),
            "agent_run_id": agent_run.get("id") if agent_run else None,
            "agent_run_status": agent_run.get("status") if agent_run else None,
            "has_questions": has_questions,
            "question_count": question_count,
        })

        # Stuck if: no questions AND (no agent run OR run is stuck in running/failed)
        if not has_questions:
            stuck_needs.append({
                "need_id": need["id"],
                "customer_id": need.get("customer", {}).get("id"),
                "customer_name": need.get("customer", {}).get("name"),
                "agent_run_id": agent_run.get("id") if agent_run else None,
                "agent_run_status": agent_run.get("status") if agent_run else None,
            })

    logger.info(
        "stuck_needs_found",
        workspace_id=workspace_id,
        total_needs=len(needs),
        stuck_count=len(stuck_needs),
    )

    if not stuck_needs:
        return RecoverStuckNeedsResponse(recovered=0, failed=0, details=[], debug=debug_info)

    # Recover each stuck need
    recovered = 0
    failed = 0
    details = []

    for stuck in stuck_needs:
        customer_id = stuck["customer_id"]
        if not customer_id:
            details.append({
                "need_id": stuck["need_id"],
                "status": "skipped",
                "reason": "No customer ID",
            })
            failed += 1
            continue

        try:
            # Fail the old stuck run if it exists and is in a non-terminal state
            old_run_id = stuck["agent_run_id"]
            old_status = stuck["agent_run_status"]
            if old_run_id and old_status in ("running", "waiting_for_input", "resuming"):
                await dc.execute_mutation(
                    "FailAgentRun",
                    {
                        "id": old_run_id,
                        "errorMessage": "Recovered: run was stuck without questions",
                        "durationMs": 0,
                    },
                )
                logger.info(
                    "failed_stuck_run",
                    run_id=old_run_id,
                    customer_name=stuck["customer_name"],
                )

            # Trigger a new handoff_auto run for this customer
            run_service = AgentRunService(dc, workspace_id)
            new_run = await run_service.create_run(
                agent_name="handoff_auto",
                trigger_type="recovery",
                triggered_by=user.uid,
                input_params={"customer_id": customer_id},
            )
            new_run_id = new_run["id"]

            # Run in background
            background_tasks.add_task(
                _run_handoff_auto_background,
                run_id=new_run_id,
                workspace_id=workspace_id,
                customer_id=customer_id,
                trigger_type="recovery",
            )

            details.append({
                "need_id": stuck["need_id"],
                "customer_id": customer_id,
                "customer_name": stuck["customer_name"],
                "old_run_id": old_run_id,
                "new_run_id": new_run_id,
                "status": "recovered",
            })
            recovered += 1

            logger.info(
                "need_recovered",
                need_id=stuck["need_id"],
                customer_id=customer_id,
                new_run_id=new_run_id,
            )

        except Exception as e:
            logger.error(
                "need_recovery_failed",
                need_id=stuck["need_id"],
                customer_id=customer_id,
                error=str(e),
            )
            details.append({
                "need_id": stuck["need_id"],
                "customer_id": customer_id,
                "status": "failed",
                "error": str(e),
            })
            failed += 1

    logger.info(
        "recover_stuck_needs_complete",
        workspace_id=workspace_id,
        recovered=recovered,
        failed=failed,
    )

    return RecoverStuckNeedsResponse(
        recovered=recovered,
        failed=failed,
        details=details,
        debug=debug_info,
    )


# =============================================================================
# Cleanup: Clear Bad Test Data
# =============================================================================


class CleanupBadDataResponse(BaseModel):
    """Response from cleanup operation."""
    needs_deleted: int
    agent_runs_deleted: int
    sidekick_items_deleted: int


class FirestoreTestResponse(BaseModel):
    """Response from Firestore test."""
    success: bool
    message: str
    emulator_host: str | None = None


class RefreshCountsResponse(BaseModel):
    """Response from refresh counts."""
    today_count: int
    sidekick_questions: int


@workspace_agents_router.post("/{workspace_id}/refresh-counts")
async def refresh_counts(
    workspace_id: str,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> RefreshCountsResponse:
    """
    Manually refresh and push all notification counts to Firestore.

    Use this to force-sync the counts when they get out of sync.
    """
    logger.info("manually_refreshing_counts", workspace_id=workspace_id)

    from services.firestore_service import get_firestore_service
    firestore = get_firestore_service()

    counts = await firestore.refresh_all_counts(workspace_id)

    logger.info(
        "counts_refreshed",
        workspace_id=workspace_id,
        **counts,
    )

    return RefreshCountsResponse(
        today_count=counts.get("today_count", 0),
        sidekick_questions=counts.get("sidekick_questions", 0),
    )


@workspace_agents_router.post("/{workspace_id}/test-firestore")
async def test_firestore(
    workspace_id: str,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> FirestoreTestResponse:
    """
    Test Firestore connectivity by writing a test notification.

    Use this to verify the Firestore emulator is working correctly.
    """
    import os
    emulator_host = os.environ.get("FIRESTORE_EMULATOR_HOST")

    logger.info(
        "testing_firestore",
        workspace_id=workspace_id,
        emulator_host=emulator_host,
    )

    try:
        from services.firestore_service import get_firestore_service
        firestore = get_firestore_service()

        # Write a test notification
        await firestore.update_workspace_notifications(
            workspace_id=workspace_id,
            sidekick_questions=999,  # Obvious test value
        )

        logger.info("firestore_test_write_success", workspace_id=workspace_id)

        return FirestoreTestResponse(
            success=True,
            message=f"Successfully wrote to notifications/{workspace_id}. Check Firestore emulator UI at http://localhost:4001",
            emulator_host=emulator_host,
        )
    except Exception as e:
        logger.error("firestore_test_failed", error=str(e))
        return FirestoreTestResponse(
            success=False,
            message=f"Firestore write failed: {str(e)}",
            emulator_host=emulator_host,
        )


@workspace_agents_router.post("/{workspace_id}/cleanup-sidekick-data")
async def cleanup_sidekick_data(
    workspace_id: str,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> CleanupBadDataResponse:
    """
    Clean up bad sidekick_question needs and their linked agent runs.

    This is a dev/test utility to clear corrupted data where multiple
    needs were incorrectly linked to the same agent run.

    Deletes:
    - All sidekick_question needs for the workspace
    - All agent runs linked to those needs
    - All sidekick items linked to those runs
    """
    logger.info("cleanup_sidekick_data_started", workspace_id=workspace_id)

    db = get_db_client()

    # Delete sidekick items first (references agent runs)
    result = await db.execute(
        '''
        DELETE FROM "SidekickItem"
        WHERE "workspaceId" = $1
        ''',
        [workspace_id],
    )
    sidekick_deleted = int(result.split()[-1]) if result else 0
    logger.info("sidekick_items_deleted", count=sidekick_deleted)

    # Delete needs of type sidekick_question
    result = await db.execute(
        '''
        DELETE FROM "Need"
        WHERE "workspaceId" = $1 AND type = 'sidekick_question'
        ''',
        [workspace_id],
    )
    needs_deleted = int(result.split()[-1]) if result else 0
    logger.info("needs_deleted", count=needs_deleted)

    # Delete agent runs that are in waiting_for_input or failed status
    result = await db.execute(
        '''
        DELETE FROM "AgentRun"
        WHERE "workspaceId" = $1
        AND status IN ('waiting_for_input', 'failed', 'running')
        ''',
        [workspace_id],
    )
    runs_deleted = int(result.split()[-1]) if result else 0
    logger.info("agent_runs_deleted", count=runs_deleted)

    logger.info(
        "cleanup_sidekick_data_complete",
        workspace_id=workspace_id,
        needs_deleted=needs_deleted,
        runs_deleted=runs_deleted,
        sidekick_deleted=sidekick_deleted,
    )

    return CleanupBadDataResponse(
        needs_deleted=needs_deleted,
        agent_runs_deleted=runs_deleted,
        sidekick_items_deleted=sidekick_deleted,
    )


# =============================================================================
# Signal Sweep (background absence/trend detectors)
# =============================================================================

class SignalSweepRequest(BaseModel):
    workspace_id: str


class SignalSweepResponse(BaseModel):
    workspace_id: str
    customers_checked: int
    signals_created: int
    skipped_dedup: int
    errors: int


@router.post("/signal-sweep/run", response_model=SignalSweepResponse)
async def run_signal_sweep(request: SignalSweepRequest) -> SignalSweepResponse:
    """
    Run absence/trend sweep detectors for a workspace.

    Detects: going_dark, engagement cadence drop, sentiment drift.
    Writes Signal rows directly (no LLM). Safe to call repeatedly — dedup-guarded.
    Intended to be called by Cloud Scheduler (nightly or hourly).
    """
    from services.signal_sweep_service import SignalSweepService

    logger.info("signal_sweep_triggered", workspace_id=request.workspace_id)

    service = SignalSweepService(request.workspace_id)
    summary = await service.run()

    return SignalSweepResponse(
        workspace_id=summary.workspace_id,
        customers_checked=summary.customers_checked,
        signals_created=summary.signals_created,
        skipped_dedup=summary.skipped_dedup,
        errors=summary.errors,
    )


# =============================================================================
# Metric Snapshot Retention (downsample old raw rows to daily)
# =============================================================================

class MetricRetentionRequest(BaseModel):
    workspace_id: str
    keep_days: int = 90


class MetricRetentionResponse(BaseModel):
    workspace_id: str
    keep_days: int
    scanned: int
    deleted: int
    kept_daily: int
    capped: bool


@router.post("/metric-retention/run", response_model=MetricRetentionResponse)
async def run_metric_retention(request: MetricRetentionRequest) -> MetricRetentionResponse:
    """Downsample MetricSnapshot rows older than keep_days to one row per
    (customer, metric, day). No-op when METRIC_SNAPSHOTS_ENABLED is off. Idempotent;
    intended for Cloud Scheduler on a slow cadence (e.g. daily/weekly)."""
    from services.metric_retention import downsample_metric_snapshots

    logger.info("metric_retention_triggered", workspace_id=request.workspace_id)
    summary = await downsample_metric_snapshots(
        request.workspace_id, keep_days=request.keep_days
    )
    return MetricRetentionResponse(
        workspace_id=summary.workspace_id,
        keep_days=summary.keep_days,
        scanned=summary.scanned,
        deleted=summary.deleted,
        kept_daily=summary.kept_daily,
        capped=summary.capped,
    )


# =============================================================================
# Pipeline Test (dev/admin — sweep + drain in one call)
# =============================================================================


class PipelineTestRequest(BaseModel):
    workspace_id: str
    steps: list[str] = ["sweep", "drain"]


class PipelineTestResponse(BaseModel):
    workspace_id: str
    sweep: dict | None = None
    drain: dict | None = None


@router.post("/pipeline-test", response_model=PipelineTestResponse)
async def run_pipeline_test(
    request: PipelineTestRequest,
    user: FirebaseUser | None = Depends(get_optional_user),
) -> PipelineTestResponse:
    """Dev/admin endpoint: run sweep + drain in one call with optional Firebase auth."""
    result = PipelineTestResponse(workspace_id=request.workspace_id)

    if "sweep" in request.steps:
        from services.signal_sweep_service import SignalSweepService

        logger.info("pipeline_test_sweep", workspace_id=request.workspace_id)
        service = SignalSweepService(request.workspace_id)
        summary = await service.run()
        result.sweep = {
            "customers_checked": summary.customers_checked,
            "signals_created": summary.signals_created,
            "skipped_dedup": summary.skipped_dedup,
            "errors": summary.errors,
            "findings": [
                {
                    "customer_name": f.customer_name,
                    "signal_kind": f.signal_kind,
                    "signal_state": f.signal_state,
                    "sentence": f.sentence,
                }
                for f in summary.findings
            ],
        }

    if "drain" in request.steps:
        import time as _time
        try:
            from orchestrator.queue.consumer import drain_workspace_detailed

            logger.info("pipeline_test_drain", workspace_id=request.workspace_id)
            t0 = _time.monotonic()
            tasks = await drain_workspace_detailed(request.workspace_id)
            duration_ms = int((_time.monotonic() - t0) * 1000)
            result.drain = {
                "processed": len(tasks),
                "duration_ms": duration_ms,
                "tasks": tasks,
            }
        except Exception as e:
            logger.warning(
                "pipeline_test_drain_failed",
                workspace_id=request.workspace_id,
                error=str(e),
            )
            result.drain = {"processed": 0, "duration_ms": 0, "tasks": [], "error": str(e)}

    return result


class PipelineResetResponse(BaseModel):
    workspace_id: str
    signals_superseded: int
    needs_resolved: int


@router.post("/pipeline-test/reset", response_model=PipelineResetResponse)
async def reset_pipeline_test(
    request: PipelineTestRequest,
    user: FirebaseUser | None = Depends(get_optional_user),
) -> PipelineResetResponse:
    """
    Reset sweep state so the pipeline test can run again cleanly.
    Supersedes all sweep-generated signals and resolves the needs they created.
    """
    from db.dataconnect_client import get_dataconnect_client

    dc = get_dataconnect_client()

    ws = request.workspace_id

    # Order matters: delete child rows before parent rows
    # 1. Risk play steps (FK → risk briefs)
    await dc.execute_mutation("DeleteRiskPlayStepsByWorkspace", {"workspaceId": ws})
    # 2. Risk briefs
    await dc.execute_mutation("DeleteRiskBriefsByWorkspace", {"workspaceId": ws})
    # 3. Draft responses (support play output)
    await dc.execute_mutation("DeleteDraftResponsesByWorkspace", {"workspaceId": ws})
    # 4. Sidekick observations/tips (record_observation output)
    await dc.execute_mutation("DeleteSidekickObservationsByWorkspace", {"workspaceId": ws})
    # 5. All open needs (except sidekick_questions which have their own flow)
    need_result = await dc.execute_mutation("ResolveAllOpenNeeds", {"workspaceId": ws})
    # 6. All active signals
    sig_result = await dc.execute_mutation("SupersedeAllActiveSignals", {"workspaceId": ws})
    # 7. Clear the AgentTask queue entirely (pending follow-ups, done, escalations) so
    #    repeated test runs don't accumulate — otherwise each drain takes exponentially longer.
    await dc.execute_mutation("DeleteAgentTasksByWorkspace", {"workspaceId": ws})

    def _count(result: dict, key: str) -> int:
        node = (result.get(key) or {})
        return int(node.get("count", 0)) if isinstance(node, dict) else 0

    signals_superseded = _count(sig_result, "signal_updateMany")
    needs_resolved = _count(need_result, "need_updateMany")

    logger.info(
        "pipeline_test_reset",
        workspace_id=ws,
        signals_superseded=signals_superseded,
        needs_resolved=needs_resolved,
    )

    return PipelineResetResponse(
        workspace_id=ws,
        signals_superseded=signals_superseded,
        needs_resolved=needs_resolved,
    )


# =============================================================================
# Inbound Support Test (dev/admin — fire fixture emails through the light lane)
# =============================================================================


class InboundTestRequest(BaseModel):
    workspace_id: str
    count: int = 12  # how many fixtures to send (cycled if > fixture count)


class InboundTestResponse(BaseModel):
    workspace_id: str
    processed: int
    duration_ms: int
    results: list[dict]


@router.post("/pipeline-test/inbound", response_model=InboundTestResponse)
async def run_inbound_test(
    request: InboundTestRequest,
    user: FirebaseUser | None = Depends(get_optional_user),
) -> InboundTestResponse:
    """
    Dev/admin endpoint: fire a batch of fake inbound emails through the light
    support lane (`run_inbound_support`).

    Fixtures are round-robined across the workspace's customers so some land on
    at-risk accounts (which carry risk signals from prior sweeps) and some on
    healthy ones — exercising the risk_analyst's escalate-vs-draft branching.
    Each fixture's intended `profile` is echoed back alongside the classifier's
    verdict so intended-vs-actual can be compared in the UI.
    """
    import time
    import uuid

    from orchestrator.plays.inbound_fixtures import INBOUND_FIXTURES
    from orchestrator.plays.support_triage import run_inbound_support
    from core.telemetry import task_trace

    ws = request.workspace_id
    logger.info("inbound_test_triggered", workspace_id=ws, count=request.count)

    dc = get_dataconnect_client()
    cust_result = await dc.execute_query("GetCustomersForSweep", {"workspaceId": ws})
    customers = cust_result.get("customers", [])

    if not customers:
        logger.warning("inbound_test_no_customers", workspace_id=ws)
        return InboundTestResponse(workspace_id=ws, processed=0, duration_ms=0, results=[])

    n_fixtures = len(INBOUND_FIXTURES)
    fixtures = [INBOUND_FIXTURES[i % n_fixtures] for i in range(max(request.count, 0))]

    results: list[dict] = []
    t0 = time.monotonic()

    async with task_trace(
        "inbound_test_batch",
        input={"count": len(fixtures), "customers": len(customers)},
        metadata={"workspace_id": ws},
        session_id=ws,
    ):
        for i, fixture in enumerate(fixtures):
            customer = customers[i % len(customers)]
            run_id = str(uuid.uuid4())
            try:
                result = await run_inbound_support(
                    workspace_id=ws,
                    customer_id=customer["id"],
                    customer_name=customer["name"],
                    subject=fixture["subject"],
                    body=fixture["body"],
                    run_id=run_id,
                )
                result["profile"] = fixture["profile"]
                results.append(result)
            except Exception as e:
                logger.warning(
                    "inbound_test_run_failed",
                    workspace_id=ws,
                    profile=fixture["profile"],
                    customer=customer.get("name"),
                    error=str(e),
                )
                results.append({"error": str(e), "profile": fixture["profile"]})

    duration_ms = int((time.monotonic() - t0) * 1000)

    logger.info(
        "inbound_test_complete",
        workspace_id=ws,
        processed=len(results),
        duration_ms=duration_ms,
    )

    return InboundTestResponse(
        workspace_id=ws,
        processed=len(results),
        duration_ms=duration_ms,
        results=results,
    )


class QueueViewRequest(BaseModel):
    workspace_id: str
    customer_id: str | None = None  # optional filter


class QueueViewResponse(BaseModel):
    workspace_id: str
    tasks: list[dict]
    counts: dict  # status → count


@router.post("/pipeline-test/queue", response_model=QueueViewResponse)
async def view_agent_task_queue(
    request: QueueViewRequest,
    user: FirebaseUser | None = Depends(get_optional_user),
) -> QueueViewResponse:
    """Pipeline console: list recent AgentTasks for a workspace (optionally filtered by
    customer), with a status rollup. Read-only view of the orchestrator queue."""
    dc = get_dataconnect_client()
    result = await dc.execute_query(
        "ListAgentTasksForWorkspace", {"workspaceId": request.workspace_id}
    )
    raw = result.get("agentTasks", [])

    tasks = []
    counts: dict[str, int] = {}
    for t in raw:
        customer = t.get("customer") or {}
        if request.customer_id and customer.get("id") != request.customer_id:
            continue
        status = t.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
        tasks.append({
            "id": t.get("id"),
            "customer_name": customer.get("name"),
            "customer_id": customer.get("id"),
            "task_type": t.get("taskType"),
            "trigger_type": t.get("triggerType"),
            "status": status,
            "priority": t.get("priority"),
            "scheduled_for": t.get("scheduledFor"),
            "attempts": t.get("attempts"),
            "created_at": t.get("createdAt"),
            "completed_at": t.get("completedAt"),
        })

    return QueueViewResponse(
        workspace_id=request.workspace_id,
        tasks=tasks,
        counts=counts,
    )

"""
Agent Run Service
Business logic for autonomous agent execution tracking and state management
Uses Firebase Data Connect for persistence.

## State Machine

All state transitions MUST go through this service to ensure consistency.

```
                                    ┌─────────────────┐
                                    │   initialized   │
                                    └────────┬────────┘
                                             │ start_run()
                                             ▼
                      ┌─────────────────► running ◄──────────────────┐
                      │                     │                         │
                      │      ┌──────────────┼──────────────┐         │
                      │      │              │              │         │
                      │      ▼              ▼              ▼         │
                      │  complete_run() pause_run()   fail_run()     │
                      │      │              │              │         │
                      │      ▼              ▼              ▼         │
                      │ ┌─────────┐  ┌─────────────┐  ┌────────┐    │
                      │ │completed│  │waiting_for_ │  │ failed │    │
                      │ │(terminal)  │   input     │  │(terminal)   │
                      │ └─────────┘  └──────┬──────┘  └────────┘    │
                      │                     │                        │
                      │                     │ resume_from_input()    │
                      │                     ▼                        │
                      │              ┌─────────────┐                 │
                      │              │  resuming   │                 │
                      │              └──────┬──────┘                 │
                      │                     │ mark_running_after_    │
                      └─────────────────────┘   resume()             │
```

Key rules:
- INITIALIZED can only → RUNNING or FAILED
- RUNNING can → WAITING_FOR_INPUT, COMPLETED, or FAILED
- WAITING_FOR_INPUT can → RESUMING or FAILED
- RESUMING can → RUNNING or FAILED
- COMPLETED and FAILED are terminal (no transitions out)

IMPORTANT: Do NOT set AgentRun status directly. Always use this service's methods.
"""

import json
from datetime import datetime, timedelta
from typing import Any

from db.dataconnect_client import DataConnectClient
from core.logging import get_logger
from core.types import (
    AgentStatus,
    ConfidenceLevel,
    ClarifyingQuestion,
    ConfidenceAssessment,
)
from core.errors import AgentNotPausedError, AgentResumeError

logger = get_logger("AgentRunService")


# Valid state transitions
VALID_TRANSITIONS = {
    AgentStatus.INITIALIZED: [AgentStatus.RUNNING, AgentStatus.FAILED],
    AgentStatus.RUNNING: [
        AgentStatus.WAITING_FOR_INPUT,
        AgentStatus.COMPLETED,
        AgentStatus.FAILED,
    ],
    AgentStatus.WAITING_FOR_INPUT: [
        AgentStatus.RESUMING,
        AgentStatus.FAILED,
    ],
    AgentStatus.RESUMING: [AgentStatus.RUNNING, AgentStatus.FAILED],
    AgentStatus.COMPLETED: [],  # Terminal state
    AgentStatus.FAILED: [],     # Terminal state
}


class AgentRunService:
    """Service for agent run lifecycle management using DataConnect."""

    def __init__(self, dc: DataConnectClient, workspace_id: str):
        self.dc = dc
        self.workspace_id = workspace_id

    async def create_run(
        self,
        agent_name: str,
        trigger_type: str = "manual",
        triggered_by: str | None = None,
        input_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Create a new agent run.

        Args:
            agent_name: Name of the agent (e.g., 'handoff_auto')
            trigger_type: How the run was triggered ('manual', 'webhook', 'poll')
            triggered_by: Who/what triggered it ('user:uuid', 'scheduler', etc.)
            input_params: Agent-specific input parameters

        Returns:
            Created agent_run record
        """
        run = await self.dc.create_agent_run(
            workspace_id=self.workspace_id,
            agent_name=agent_name,
            trigger_type=trigger_type,
            triggered_by=triggered_by,
            input_params=input_params,
        )

        logger.info(
            "agent_run_created",
            run_id=str(run.get("id")),
            agent_name=agent_name,
            trigger_type=trigger_type,
        )

        return run

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Get an agent run by ID."""
        run = await self.dc.get_agent_run(run_id)
        if run:
            # Normalize UUIDs for comparison (handle with/without hyphens)
            run_workspace_id = run.get("workspace", {}).get("id", "").replace("-", "")
            expected_workspace_id = self.workspace_id.replace("-", "")
            if run_workspace_id != expected_workspace_id:
                return None  # Don't return runs from other workspaces
        return run

    async def start_run(self, run_id: str) -> dict[str, Any]:
        """
        Transition run from INITIALIZED to RUNNING.

        Args:
            run_id: The agent run UUID

        Returns:
            Updated run record
        """
        run = await self.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        # Idempotent: if already running, return current state
        if not self._validate_transition(run, AgentStatus.RUNNING):
            return run
        return await self.dc.start_agent_run(run_id)

    async def update_step(
        self,
        run_id: str,
        step_name: str,
        context_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Update the current step and optionally snapshot context.

        Args:
            run_id: The agent run UUID
            step_name: Current step name
            context_snapshot: Serialized context for resume

        Returns:
            Updated run record
        """
        return await self.dc.update_agent_run_step(
            run_id=run_id,
            step_name=step_name,
            context_snapshot=context_snapshot,
        )

    async def pause_for_input(
        self,
        run_id: str,
        confidence: ConfidenceAssessment,
        questions: list[ClarifyingQuestion],
        blocking_need_id: str,
        context_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Pause the agent run to wait for human input.

        Args:
            run_id: The agent run UUID
            confidence: Confidence assessment that triggered the pause
            questions: List of clarifying questions
            blocking_need_id: The need created for the user to answer
            context_snapshot: Serialized context for resume

        Returns:
            Updated run record
        """
        run = await self.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        # Idempotent: if already waiting_for_input, return current state
        if not self._validate_transition(run, AgentStatus.WAITING_FOR_INPUT):
            return run

        return await self.dc.pause_agent_run(
            run_id=run_id,
            pause_reason=f"confidence_{confidence.level.value}",
            confidence_level=confidence.level.value,
            confidence_score=confidence.score,
            confidence_reasons=confidence.reasons,
            clarifying_questions=[q.model_dump() for q in questions],
            blocking_need_id=blocking_need_id,
            context_snapshot=context_snapshot,
        )

    async def pause_run(
        self,
        run_id: str,
        pause_reason: str,
        clarifying_questions: list[dict[str, Any]] | None = None,
        blocking_need_id: str | None = None,
        context_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Pause the agent run with a reason (simplified version).

        Args:
            run_id: The agent run UUID
            pause_reason: Why the agent is pausing
            clarifying_questions: Optional list of questions (as dicts)
            blocking_need_id: Optional need ID that blocks the run
            context_snapshot: Optional context for resume

        Returns:
            Updated run record
        """
        run = await self.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        # Idempotent: if already waiting_for_input, return current state
        if not self._validate_transition(run, AgentStatus.WAITING_FOR_INPUT):
            return run

        return await self.dc.pause_agent_run(
            run_id=run_id,
            pause_reason=pause_reason,
            clarifying_questions=clarifying_questions,
            blocking_need_id=blocking_need_id,
            context_snapshot=context_snapshot,
        )

    async def resume_from_input(
        self,
        run_id: str,
        answers: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Resume a paused agent run with human-provided answers.

        Also handles recovering failed runs - if a run failed but has questions,
        the user should still be able to submit answers and restart the agent.

        Args:
            run_id: The agent run UUID
            answers: Answers to the clarifying questions

        Returns:
            Updated run record

        Raises:
            AgentNotPausedError: If run is not in a resumable state
        """
        run = await self.get_run(run_id)
        if not run:
            raise AgentResumeError("Run not found", run_id)

        # Accept waiting_for_input, resuming, or failed (for recovery)
        # When a run is failed but has questions, the user should still be able
        # to submit answers and recover the run
        valid_statuses = (
            AgentStatus.WAITING_FOR_INPUT.value,
            AgentStatus.RESUMING.value,
            AgentStatus.FAILED.value,
        )
        if run["status"] not in valid_statuses:
            raise AgentNotPausedError(run_id, run["status"])

        # Log if we're recovering a failed run
        if run["status"] == AgentStatus.FAILED.value:
            logger.info(
                "recovering_failed_run",
                run_id=run_id,
                previous_status="failed",
            )

        # Update status to resuming
        await self.dc.resume_agent_run(run_id, answers)

        # Return the full run data (mutation only returns minimal data)
        # Parse JSON fields that the caller expects
        result = dict(run)

        if result.get("contextSnapshot"):
            try:
                result["context_snapshot"] = json.loads(result["contextSnapshot"])
            except (json.JSONDecodeError, TypeError):
                result["context_snapshot"] = {}
        else:
            result["context_snapshot"] = {}

        if result.get("inputParams"):
            try:
                result["input_params"] = json.loads(result["inputParams"])
            except (json.JSONDecodeError, TypeError):
                result["input_params"] = {}
        else:
            result["input_params"] = {}

        return result

    async def mark_running_after_resume(self, run_id: str) -> dict[str, Any]:
        """Transition from RESUMING back to RUNNING."""
        run = await self.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        # Idempotent: if already running, return current state
        if not self._validate_transition(run, AgentStatus.RUNNING):
            return run
        return await self.dc.mark_agent_run_running(run_id)

    async def complete_run(
        self,
        run_id: str,
        result: dict[str, Any],
        customer_id: str | None = None,
        brief_id: str | None = None,
        plan_id: str | None = None,
        used_fallback: bool = False,
        fallback_reason: str | None = None,
    ) -> dict[str, Any]:
        """
        Mark an agent run as completed successfully.

        Args:
            run_id: The agent run UUID
            result: Final result data
            customer_id: Created customer ID
            brief_id: Created handoff brief ID
            plan_id: Created AI plan ID
            used_fallback: Whether a fallback was used
            fallback_reason: Why fallback was needed

        Returns:
            Updated run record
        """
        run = await self.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        # Idempotent: if already completed, return current state
        if not self._validate_transition(run, AgentStatus.COMPLETED):
            return run

        # Calculate duration
        duration_ms = None
        started_at = run.get("startedAt")
        if started_at:
            if isinstance(started_at, str):
                started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            duration_ms = int((datetime.utcnow().replace(tzinfo=started_at.tzinfo) - started_at).total_seconds() * 1000)

        return await self.dc.complete_agent_run(
            run_id=run_id,
            result_data=result,
            customer_id=customer_id,
            brief_id=brief_id,
            plan_id=plan_id,
            used_fallback=used_fallback,
            fallback_reason=fallback_reason,
            duration_ms=duration_ms,
        )

    async def fail_run(
        self,
        run_id: str,
        error_message: str,
        context_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Mark an agent run as failed.

        Args:
            run_id: The agent run UUID
            error_message: Description of the failure
            context_snapshot: Final context state for debugging

        Returns:
            Updated run record
        """
        run = await self.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        # Idempotent: if already failed, return current state
        if not self._validate_transition(run, AgentStatus.FAILED):
            return run

        # Calculate duration
        duration_ms = None
        started_at = run.get("startedAt")
        if started_at:
            if isinstance(started_at, str):
                started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            duration_ms = int((datetime.utcnow().replace(tzinfo=started_at.tzinfo) - started_at).total_seconds() * 1000)

        return await self.dc.fail_agent_run(
            run_id=run_id,
            error_message=error_message,
            context_snapshot=context_snapshot,
            duration_ms=duration_ms,
        )

    async def get_waiting_runs(
        self,
        agent_name: str | None = None,
        max_age_hours: int = 168,  # 7 days
    ) -> list[dict[str, Any]]:
        """
        Get runs waiting for input that have been answered.

        Args:
            agent_name: Filter by agent name
            max_age_hours: Max age of paused runs to consider

        Returns:
            List of runs with answered blocking needs
        """
        runs = await self.dc.get_waiting_runs(self.workspace_id, agent_name)

        # Filter by max age and resolved blocking needs
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        result = []
        for run in runs:
            paused_at = run.get("pausedAt")
            if paused_at:
                if isinstance(paused_at, str):
                    paused_at = datetime.fromisoformat(paused_at.replace("Z", "+00:00"))
                if paused_at.replace(tzinfo=None) < cutoff:
                    continue

            # Check if blocking need is resolved
            blocking_need = run.get("blockingNeed")
            if blocking_need and blocking_need.get("resolvedAt"):
                result.append(run)

        return result

    async def get_timed_out_runs(
        self,
        timeout_hours: int = 24,
    ) -> list[dict[str, Any]]:
        """
        Get runs that have been waiting for input longer than timeout.

        Args:
            timeout_hours: Hours after which a paused run times out

        Returns:
            List of timed out runs
        """
        runs = await self.dc.get_waiting_runs(self.workspace_id)

        # Filter by timeout
        cutoff = datetime.utcnow() - timedelta(hours=timeout_hours)
        result = []
        for run in runs:
            paused_at = run.get("pausedAt")
            if paused_at:
                if isinstance(paused_at, str):
                    paused_at = datetime.fromisoformat(paused_at.replace("Z", "+00:00"))
                if paused_at.replace(tzinfo=None) < cutoff:
                    # Check if blocking need is NOT resolved
                    blocking_need = run.get("blockingNeed")
                    if not blocking_need or not blocking_need.get("resolvedAt"):
                        result.append(run)

        return result

    async def get_active_run(self, agent_name: str) -> dict[str, Any] | None:
        """
        Check if there's an active (non-terminal) run for this agent.

        Args:
            agent_name: The agent name

        Returns:
            Active run record if one exists
        """
        return await self.dc.get_active_agent_run(self.workspace_id, agent_name)

    def _validate_transition(self, run: dict[str, Any], new_status: AgentStatus) -> bool:
        """
        Validate that a status transition is allowed.

        Returns:
            True if transition should proceed, False if already in target state (idempotent)

        Raises:
            ValueError if transition is invalid
        """
        current_status = AgentStatus(run["status"])

        # Idempotent: if already in target state, no-op
        if current_status == new_status:
            logger.debug(
                "agent_run_transition_idempotent",
                run_id=run.get("id"),
                status=current_status.value,
            )
            return False

        valid_targets = VALID_TRANSITIONS.get(current_status, [])

        if new_status not in valid_targets:
            raise ValueError(
                f"Invalid transition: {current_status.value} -> {new_status.value}. "
                f"Valid targets: {[s.value for s in valid_targets]}"
            )

        logger.info(
            "agent_run_transition_validated",
            run_id=run.get("id"),
            from_status=current_status.value,
            to_status=new_status.value,
        )
        return True

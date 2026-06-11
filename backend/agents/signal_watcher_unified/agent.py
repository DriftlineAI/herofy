"""
SignalWatcher Auto Agent
Entry point for autonomous signal processing with confidence-aware pause/resume
"""

from dataclasses import dataclass
from typing import Any

from .loop_controller import SignalWatcherLoopController


@dataclass
class SignalWatcherAutoResult:
    """Result from SignalWatcher auto execution."""

    run_id: str
    status: str  # "completed" | "waiting_for_input" | "failed"
    signals_processed: int = 0
    needs_created: int = 0
    threads_created: int = 0
    interactions_created: int = 0
    stakeholders_updated: int = 0
    need_id: str | None = None  # If paused, the need to answer
    questions: list[dict[str, Any]] | None = None  # If paused, the questions
    error: str | None = None


async def run_signal_watcher_auto(
    workspace_id: str,
    trigger_type: str = "scheduled",
    triggered_by: str | None = None,
    settings_override: dict[str, Any] | None = None,
) -> SignalWatcherAutoResult:
    """
    Run the autonomous signal watcher agent.

    This is the main entry point for confidence-aware signal processing.
    Unlike signal_watcher_chain, this version can:
    - Assess confidence in classifications and matches
    - Pause for human input when confidence is low
    - Resume processing after receiving answers

    Args:
        workspace_id: The workspace UUID
        trigger_type: How this run was triggered (scheduled, manual, webhook)
        triggered_by: Who/what triggered it
        settings_override: Override workspace settings for this run

    Returns:
        SignalWatcherAutoResult with status and counts
    """
    controller = SignalWatcherLoopController(workspace_id)

    result = await controller.run(
        trigger_type=trigger_type,
        triggered_by=triggered_by,
        settings_override=settings_override,
    )

    return SignalWatcherAutoResult(
        run_id=result.get("run_id", ""),
        status=result.get("status", "failed"),
        signals_processed=result.get("signals_processed", 0),
        needs_created=result.get("needs_created", 0),
        threads_created=result.get("threads_created", 0),
        interactions_created=result.get("interactions_created", 0),
        stakeholders_updated=result.get("stakeholders_updated", 0),
        need_id=result.get("need_id"),
        questions=result.get("questions"),
        error=result.get("error"),
    )


async def resume_signal_watcher_auto(
    workspace_id: str,
    run_id: str,
    answers: dict[str, Any],
) -> SignalWatcherAutoResult:
    """
    Resume a paused signal watcher run with provided answers.

    Args:
        workspace_id: The workspace UUID
        run_id: The paused run ID
        answers: Answers to the clarifying questions

    Returns:
        SignalWatcherAutoResult with status and counts
    """
    controller = SignalWatcherLoopController(workspace_id)

    result = await controller.resume(
        run_id=run_id,
        answers=answers,
    )

    return SignalWatcherAutoResult(
        run_id=result.get("run_id", run_id),
        status=result.get("status", "failed"),
        signals_processed=result.get("signals_processed", 0),
        needs_created=result.get("needs_created", 0),
        threads_created=result.get("threads_created", 0),
        interactions_created=result.get("interactions_created", 0),
        stakeholders_updated=result.get("stakeholders_updated", 0),
        need_id=result.get("need_id"),
        questions=result.get("questions"),
        error=result.get("error"),
    )

"""
SignalWatcher Chain Agent
Autonomous agent for processing incoming signals using sequential steps

This agent uses a sequential pattern (like HandoffChain) to process signals.
It runs 7 steps in order, creating interactions, threads, and needs.

For confidence-aware autonomous mode with pause/resume, see signal_watcher_auto.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from config import settings
from core.errors import StepFailedError
from core.logging import get_logger, bind_context, clear_context
from tools.database_tool import get_handbook_version, insert_need

from .context import SignalWatcherContext
from .steps import (
    fetch_signals_step,
    classify_signals_step,
    match_threads_step,
    match_needs_step,
    extract_profiles_step,
    create_interactions_step,
    update_watermarks_step,
)

logger = get_logger("SignalWatcherChainAgent")

# Step timeout in seconds
STEP_TIMEOUT = 60


@dataclass
class SignalWatcherChainResult:
    """Result from SignalWatcher chain execution."""

    run_id: str
    status: str  # "completed" | "failed"
    signals_processed: int = 0
    needs_created: int = 0
    threads_created: int = 0
    interactions_created: int = 0
    stakeholders_updated: int = 0
    error: str | None = None
    duration_ms: int | None = None


async def run_signal_watcher_chain(
    workspace_id: str,
) -> SignalWatcherChainResult:
    """
    Run the SignalWatcher chain agent to process incoming signals.

    This is the main entry point for the sequential signal watcher.
    It orchestrates 7 steps:
    1. FetchSignalsStep - Get new signals from Gmail/Slack/Notion
    2. ClassifySignalsStep - Classify each signal (need_type, sentiment)
    3. MatchThreadsStep - Match signals to existing threads
    4. MatchNeedsStep - Match to existing needs or create new
    5. ExtractProfilesStep - Update stakeholder profiles
    6. CreateInteractionsStep - Create interaction records
    7. UpdateWatermarksStep - Update source watermarks

    Args:
        workspace_id: The workspace UUID

    Returns:
        SignalWatcherChainResult with status and counts
    """
    start_time = datetime.utcnow()

    # Initialize context
    ctx = SignalWatcherContext(workspace_id=workspace_id)

    # Bind logging context
    bind_context(
        run_id=ctx.run_id,
        workspace_id=workspace_id,
        agent="SignalWatcherChain",
    )

    logger.info("agent_started", workspace_id=workspace_id)

    try:
        # Get handbook version for audit trail
        handbook_version = await get_handbook_version(workspace_id)
        if handbook_version:
            ctx.handbook_version_id = handbook_version["id"]
        else:
            logger.warning("no_handbook_version_found", workspace_id=workspace_id)

        # Execute steps sequentially
        ctx = await _run_step_with_timeout(
            "FetchSignalsStep",
            lambda c: fetch_signals_step(c),
            ctx,
        )

        # Skip remaining steps if no signals
        if ctx.signal_count == 0:
            logger.info("no_signals_to_process", run_id=ctx.run_id)
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            return SignalWatcherChainResult(
                run_id=ctx.run_id,
                status="completed",
                signals_processed=0,
                duration_ms=duration_ms,
            )

        ctx = await _run_step_with_timeout(
            "ClassifySignalsStep",
            lambda c: classify_signals_step(c),
            ctx,
        )

        ctx = await _run_step_with_timeout(
            "MatchThreadsStep",
            lambda c: match_threads_step(c),
            ctx,
        )

        ctx = await _run_step_with_timeout(
            "MatchNeedsStep",
            lambda c: match_needs_step(c),
            ctx,
        )

        ctx = await _run_step_with_timeout(
            "ExtractProfilesStep",
            lambda c: extract_profiles_step(c),
            ctx,
        )

        ctx = await _run_step_with_timeout(
            "CreateInteractionsStep",
            lambda c: create_interactions_step(c),
            ctx,
        )

        ctx = await _run_step_with_timeout(
            "UpdateWatermarksStep",
            lambda c: update_watermarks_step(c),
            ctx,
        )

        # Calculate duration
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        logger.info(
            "agent_completed",
            duration_ms=duration_ms,
            signals_processed=len(ctx.processed_signals),
            needs_created=len(ctx.created_needs),
            threads_created=len(ctx.created_threads),
            interactions_created=len(ctx.created_interactions),
        )

        return SignalWatcherChainResult(
            run_id=ctx.run_id,
            status="completed",
            signals_processed=len(ctx.processed_signals),
            needs_created=len(ctx.created_needs),
            threads_created=len(ctx.created_threads),
            interactions_created=len(ctx.created_interactions),
            stakeholders_updated=len(ctx.stakeholder_profiles),
            duration_ms=duration_ms,
        )

    except StepFailedError as e:
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        logger.error(
            "agent_failed",
            step=e.step_name,
            error=e.message,
            duration_ms=duration_ms,
        )

        # Surface error as need
        await _surface_error_need(ctx, e)

        return SignalWatcherChainResult(
            run_id=ctx.run_id,
            status="failed",
            signals_processed=len(ctx.raw_signals),
            needs_created=len(ctx.created_needs),
            error=f"{e.step_name}: {e.message}",
            duration_ms=duration_ms,
        )

    except Exception as e:
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        logger.exception(
            "agent_error",
            error=str(e),
            duration_ms=duration_ms,
        )

        return SignalWatcherChainResult(
            run_id=ctx.run_id,
            status="failed",
            error=str(e),
            duration_ms=duration_ms,
        )

    finally:
        clear_context()


async def _run_step_with_timeout(
    step_name: str,
    step_fn,
    ctx: SignalWatcherContext,
) -> SignalWatcherContext:
    """
    Run a step with timeout.

    Args:
        step_name: Name of the step for logging
        step_fn: Async function to execute
        ctx: Current context

    Returns:
        Updated context

    Raises:
        StepFailedError: If step fails or times out
    """
    try:
        return await asyncio.wait_for(
            step_fn(ctx),
            timeout=STEP_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise StepFailedError(
            f"Step timed out after {STEP_TIMEOUT}s",
            step_name=step_name,
        )


async def _surface_error_need(ctx: SignalWatcherContext, error: StepFailedError) -> None:
    """
    Surface an error as a need in the Today queue.

    This ensures CSMs are notified when signal processing fails.
    """
    try:
        # Only create need if we have handbook version
        if not ctx.handbook_version_id:
            logger.warning("cannot_surface_error_need", reason="no_handbook_version")
            return

        # Need a customer_id to create a need - use first processed customer
        customer_id = None
        for signal in ctx.classified_signals:
            if signal.customer_id:
                customer_id = signal.customer_id
                break

        if not customer_id:
            logger.warning("cannot_surface_error_need", reason="no_customer")
            return

        await insert_need(
            workspace_id=ctx.workspace_id,
            customer_id=customer_id,
            need_type="uncategorized",
            headline=f"SignalWatcher failed: {error.step_name}",
            lede=f"Run ID: {ctx.run_id}",
            agent_reasoning=f"""SignalWatcher agent failed during step: {error.step_name}

Error: {error.message}

Run context:
- Signals fetched: {len(ctx.raw_signals)}
- Signals classified: {len(ctx.classified_signals)}
- Threads matched: {len([m for m in ctx.thread_matches.values() if m])}
- Needs matched: {len([m for m in ctx.need_matches.values() if m])}

Please investigate and manually review any pending signals.""",
            handbook_version_id=ctx.handbook_version_id,
            priority_rank=5,  # Higher priority for errors
        )

        logger.info(
            "error_need_surfaced",
            step=error.step_name,
            customer_id=customer_id,
        )

    except Exception as e:
        logger.error(
            "failed_to_surface_error_need",
            error=str(e),
        )

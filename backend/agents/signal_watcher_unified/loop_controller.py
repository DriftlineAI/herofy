"""
Signal Watcher Loop Controller
State machine orchestrator for autonomous signal processing with pause/resume
"""

import asyncio
from datetime import datetime
from typing import Any
from uuid import uuid4

from config import settings
from core.logging import get_logger, bind_context, clear_context
from core.types import (
    AgentStatus,
    ConfidenceAssessment,
    ClarifyingQuestion,
    NeedType,
    WorkspaceAgentSettings,
)
from core.errors import (
    PauseForInputSignal,
    AgentError,
    StepFailedError,
)
from db.dataconnect_client import get_dataconnect_client
from services.agent_run_service import AgentRunService
from services.health_scoring_service import HealthScoringService
from tools.database_tool import get_handbook_version, insert_need

# Import chain steps (reuse for DRY)
from agents.signal_watcher_legacy.steps import (
    fetch_signals_step,
    classify_signals_step,
    match_threads_step,
    match_needs_step,
    extract_profiles_step,
    create_interactions_step,
    update_watermarks_step,
)
from agents.signal_watcher_legacy.context import SignalWatcherContext

from .confidence import (
    assess_batch_confidence,
    should_pause_for_signal,
)

logger = get_logger("SignalWatcherLoopController")

# Step timeout in seconds
STEP_TIMEOUT = 120


class SignalWatcherLoopController:
    """
    Orchestrates autonomous signal processing with confidence-aware pause/resume.

    Uses the signal_watcher_chain steps but wraps them with:
    - State persistence for pause/resume
    - Confidence checking after matching steps
    - Automatic resume when answers arrive
    """

    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id
        self.dc = get_dataconnect_client()
        self.run_service = AgentRunService(self.dc, workspace_id)
        self._settings: WorkspaceAgentSettings | None = None

    async def _get_settings(self) -> WorkspaceAgentSettings | None:
        """Get agent settings for this workspace."""
        if self._settings is None:
            try:
                result = await self.dc.execute_query(
                    "GetWorkspaceAgentSettings",
                    {
                        "workspaceId": self.workspace_id,
                        "agentName": "signal_watcher_auto",
                    },
                )

                settings_list = result.get("workspaceAgentSettings", [])
                if settings_list:
                    # Convert camelCase from GraphQL to snake_case for Pydantic
                    row = settings_list[0]
                    settings_dict = {
                        "workspace_id": self.workspace_id,
                        "agent_name": row.get("agentName"),
                        "autonomy_mode": row.get("autonomyMode"),
                        "pause_on_medium_confidence": row.get("pauseOnMediumConfidence"),
                        "question_timeout_hours": row.get("questionTimeoutHours"),
                        "fallback_on_timeout": row.get("fallbackOnTimeout"),
                        "notify_on_pause": row.get("notifyOnPause"),
                        "notify_on_complete": row.get("notifyOnComplete"),
                        "enabled": row.get("enabled"),
                    }
                    self._settings = WorkspaceAgentSettings(**settings_dict)
            except Exception as e:
                logger.warning("workspace_settings_not_available", error=str(e))
                # Return None - will use defaults
        return self._settings

    async def run(
        self,
        trigger_type: str = "scheduled",
        triggered_by: str | None = None,
        settings_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Run the autonomous signal watcher agent.

        Args:
            trigger_type: How this run was triggered (scheduled, manual, webhook)
            triggered_by: Who/what triggered it
            settings_override: Override workspace settings for this run

        Returns:
            Run result with status, counts, and any pause information
        """
        # Create the run record
        run = await self.run_service.create_run(
            agent_name="signal_watcher_auto",
            trigger_type=trigger_type,
            triggered_by=triggered_by,
            input_params={
                "settings_override": settings_override,
            },
        )
        run_id = str(run["id"])

        # Bind logging context
        bind_context(
            run_id=run_id,
            workspace_id=self.workspace_id,
            agent="signal_watcher_auto",
        )

        logger.info(
            "run_started",
            trigger_type=trigger_type,
        )

        try:
            # Start the run
            await self.run_service.start_run(run_id)

            # Execute the loop
            result = await self._execute_loop(
                run_id=run_id,
                settings_override=settings_override,
            )

            return result

        except PauseForInputSignal as pause:
            # Agent paused for input - expected control flow
            logger.info(
                "run_paused",
                run_id=run_id,
                need_id=pause.need_id,
                question_count=len(pause.questions),
            )
            return {
                "run_id": run_id,
                "status": AgentStatus.WAITING_FOR_INPUT.value,
                "need_id": pause.need_id,
                "questions": pause.questions,
            }

        except Exception as e:
            logger.exception("run_failed", error=str(e))
            await self.run_service.fail_run(run_id, str(e))
            return {
                "run_id": run_id,
                "status": AgentStatus.FAILED.value,
                "error": str(e),
            }

        finally:
            clear_context()

    async def resume(
        self,
        run_id: str,
        answers: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Resume a paused agent run with provided answers.

        Args:
            run_id: The paused run ID
            answers: Answers to the clarifying questions

        Returns:
            Run result with status and counts
        """
        bind_context(
            run_id=run_id,
            workspace_id=self.workspace_id,
            agent="signal_watcher_auto",
        )

        logger.info(
            "run_resuming",
            run_id=run_id,
            answer_count=len(answers),
        )

        try:
            # Update run state to resuming
            run = await self.run_service.resume_from_input(run_id, answers)

            # Get the context snapshot
            context_snapshot = run.get("context_snapshot", {})
            settings_override = run.get("input_params", {}).get("settings_override")

            # Transition to running
            await self.run_service.mark_running_after_resume(run_id)

            # Continue execution from where we paused
            result = await self._execute_loop(
                run_id=run_id,
                settings_override=settings_override,
                context_snapshot=context_snapshot,
                resume_answers=answers,
                resume_from_step=run.get("current_step"),
            )

            return result

        except PauseForInputSignal as pause:
            # Paused again
            logger.info(
                "run_paused_again",
                run_id=run_id,
                need_id=pause.need_id,
            )
            return {
                "run_id": run_id,
                "status": AgentStatus.WAITING_FOR_INPUT.value,
                "need_id": pause.need_id,
                "questions": pause.questions,
            }

        except Exception as e:
            logger.exception("resume_failed", error=str(e))
            await self.run_service.fail_run(run_id, str(e))
            return {
                "run_id": run_id,
                "status": AgentStatus.FAILED.value,
                "error": str(e),
            }

        finally:
            clear_context()

    async def _execute_loop(
        self,
        run_id: str,
        settings_override: dict[str, Any] | None = None,
        context_snapshot: dict[str, Any] | None = None,
        resume_answers: dict[str, Any] | None = None,
        resume_from_step: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute the main agent loop.

        Reuses signal_watcher_chain steps with confidence checking.
        """
        # Get settings
        workspace_settings = await self._get_settings()

        # Initialize or restore context
        if context_snapshot:
            try:
                ctx = SignalWatcherContext.from_dict(context_snapshot)
                # Apply answers if resuming
                if resume_answers:
                    ctx = self._apply_answers(ctx, resume_answers)
            except Exception as e:
                logger.error(
                    "context_deserialization_failed",
                    run_id=run_id,
                    error=str(e),
                )
                raise AgentError(
                    f"Failed to restore agent context: {e}",
                    code="CONTEXT_RESTORE_FAILED",
                )
        else:
            ctx = SignalWatcherContext(workspace_id=self.workspace_id)

        # Get handbook version
        handbook_version = await get_handbook_version(self.workspace_id)
        if handbook_version:
            ctx.handbook_version_id = handbook_version["id"]

        # Define step sequence with confidence check inserted
        steps = [
            ("fetch_signals", self._step_fetch_signals),
            ("classify_signals", self._step_classify_signals),
            ("match_threads", self._step_match_threads),
            ("match_needs", self._step_match_needs),
            ("confidence_check", self._step_confidence_check),  # Our key addition
            ("extract_profiles", self._step_extract_profiles),
            ("create_interactions", self._step_create_interactions),
            ("update_watermarks", self._step_update_watermarks),
            ("update_health_scores", self._step_update_health_scores),
        ]

        # Find starting step
        start_index = 0
        if resume_from_step:
            for i, (name, _) in enumerate(steps):
                if name == resume_from_step:
                    # Skip confidence check on resume (answers already applied)
                    if name == "confidence_check":
                        start_index = i + 1
                    else:
                        start_index = i
                    break

        # Execute steps
        for i in range(start_index, len(steps)):
            step_name, step_fn = steps[i]

            # Skip remaining steps if no signals
            if step_name != "fetch_signals" and ctx.signal_count == 0:
                logger.info("skipping_steps_no_signals", step=step_name)
                break

            await self.run_service.update_step(
                run_id,
                step_name,
                ctx.to_dict(),
            )

            try:
                ctx = await asyncio.wait_for(
                    step_fn(ctx, run_id, workspace_settings),
                    timeout=STEP_TIMEOUT,
                )
            except asyncio.TimeoutError:
                raise StepFailedError(
                    f"Step timed out after {STEP_TIMEOUT}s",
                    step_name=step_name,
                )

        # Complete the run
        result = {
            "signals_processed": len(ctx.processed_signals),
            "needs_created": len(ctx.created_needs),
            "threads_created": len(ctx.created_threads),
            "interactions_created": len(ctx.created_interactions),
            "stakeholders_updated": len(ctx.stakeholder_profiles),
        }

        await self.run_service.complete_run(
            run_id=run_id,
            result=result,
        )

        logger.info(
            "run_completed",
            run_id=run_id,
            **result,
        )

        return {
            "run_id": run_id,
            "status": AgentStatus.COMPLETED.value,
            **result,
        }

    # =========================================================================
    # Step Wrappers
    # =========================================================================

    async def _step_fetch_signals(
        self,
        ctx: SignalWatcherContext,
        run_id: str,
        settings: WorkspaceAgentSettings | None,
    ) -> SignalWatcherContext:
        """Wrap fetch_signals_step from chain."""
        return await fetch_signals_step(ctx)

    async def _step_classify_signals(
        self,
        ctx: SignalWatcherContext,
        run_id: str,
        settings: WorkspaceAgentSettings | None,
    ) -> SignalWatcherContext:
        """Wrap classify_signals_step from chain."""
        return await classify_signals_step(ctx)

    async def _step_match_threads(
        self,
        ctx: SignalWatcherContext,
        run_id: str,
        settings: WorkspaceAgentSettings | None,
    ) -> SignalWatcherContext:
        """Wrap match_threads_step from chain."""
        return await match_threads_step(ctx)

    async def _step_match_needs(
        self,
        ctx: SignalWatcherContext,
        run_id: str,
        settings: WorkspaceAgentSettings | None,
    ) -> SignalWatcherContext:
        """Wrap match_needs_step from chain."""
        return await match_needs_step(ctx)

    async def _step_confidence_check(
        self,
        ctx: SignalWatcherContext,
        run_id: str,
        settings: WorkspaceAgentSettings | None,
    ) -> SignalWatcherContext:
        """
        Check confidence and pause if needed.
        This is our key addition to the chain flow.
        """
        # Assess batch confidence
        assessment, low_confidence_signals = assess_batch_confidence(
            signals=ctx.classified_signals,
            thread_matches=ctx.thread_matches,
            need_matches=ctx.need_matches,
        )

        # Check if we should pause
        if should_pause_for_signal(assessment, settings):
            # Create need for user to review
            need_id = await self._create_review_need(
                ctx=ctx,
                run_id=run_id,
                assessment=assessment,
                low_confidence_signals=low_confidence_signals,
            )

            # Save context for resume
            context_snapshot = ctx.to_dict()

            # Pause the run
            await self.run_service.pause_for_input(
                run_id=run_id,
                confidence=assessment,
                questions=assessment.questions or [],
                blocking_need_id=need_id,
                context_snapshot=context_snapshot,
            )

            # Raise signal to stop execution
            raise PauseForInputSignal(
                need_id=need_id,
                questions=[q.model_dump() for q in (assessment.questions or [])],
                context=context_snapshot,
                run_id=run_id,
            )

        # Continue if confident
        logger.info(
            "confidence_check_passed",
            level=assessment.level.value,
            score=assessment.score,
            signal_count=len(ctx.classified_signals),
        )

        return ctx

    async def _step_extract_profiles(
        self,
        ctx: SignalWatcherContext,
        run_id: str,
        settings: WorkspaceAgentSettings | None,
    ) -> SignalWatcherContext:
        """Wrap extract_profiles_step from chain."""
        return await extract_profiles_step(ctx)

    async def _step_create_interactions(
        self,
        ctx: SignalWatcherContext,
        run_id: str,
        settings: WorkspaceAgentSettings | None,
    ) -> SignalWatcherContext:
        """Wrap create_interactions_step from chain."""
        return await create_interactions_step(ctx)

    async def _step_update_watermarks(
        self,
        ctx: SignalWatcherContext,
        run_id: str,
        settings: WorkspaceAgentSettings | None,
    ) -> SignalWatcherContext:
        """Wrap update_watermarks_step from chain."""
        return await update_watermarks_step(ctx)

    async def _step_update_health_scores(
        self,
        ctx: SignalWatcherContext,
        run_id: str,
        settings: WorkspaceAgentSettings | None,
    ) -> SignalWatcherContext:
        """
        Update health scores for affected customers.

        After processing signals, recalculate relationship health for any
        customers whose signals were classified or updated.
        """
        # Get unique customer IDs from processed signals
        customer_ids = set()
        for signal in ctx.classified_signals:
            if signal.customer_id:
                customer_ids.add(signal.customer_id)

        if not customer_ids:
            logger.info("no_customers_to_update_health", signal_count=len(ctx.classified_signals))
            return ctx

        logger.info(
            "updating_customer_health_scores",
            customer_count=len(customer_ids),
            signal_count=len(ctx.classified_signals),
        )

        # Initialize health scoring service
        health_service = HealthScoringService(self.dc, self.workspace_id)

        # Update each customer's health score
        updated_count = 0
        failed_count = 0

        for customer_id in customer_ids:
            try:
                result = await health_service.calculate_health(
                    customer_id,
                    updated_by="system:signal_watcher_auto",
                )

                logger.info(
                    "customer_health_updated",
                    customer_id=customer_id,
                    score=result.score,
                    health=result.health,
                    reason=result.reason,
                )

                updated_count += 1

            except Exception as e:
                logger.error(
                    "customer_health_update_failed",
                    customer_id=customer_id,
                    error=str(e),
                )
                failed_count += 1

        logger.info(
            "health_score_update_complete",
            updated=updated_count,
            failed=failed_count,
            total=len(customer_ids),
        )

        return ctx

    # =========================================================================
    # Helpers
    # =========================================================================

    async def _create_review_need(
        self,
        ctx: SignalWatcherContext,
        run_id: str,
        assessment: ConfidenceAssessment,
        low_confidence_signals: list[str],
    ) -> str:
        """Create a need in Today Queue for user to review signals."""
        questions = assessment.questions or []

        # Format questions for display
        questions_text = "\n".join(
            f"**{i+1}. {q.question}**\n   _{q.context or ''}_"
            for i, q in enumerate(questions)
        )

        # Get first customer_id from signals if available
        customer_id = None
        for signal in ctx.classified_signals:
            if signal.customer_id:
                customer_id = signal.customer_id
                break

        reasoning = f"""The signal watcher agent needs clarification before proceeding.

**Confidence Level**: {assessment.level.value.upper()} ({assessment.score:.0%})

**Signals requiring review**: {len(low_confidence_signals)} of {len(ctx.classified_signals)}

**Reasons for pause**:
{chr(10).join(f'- {r}' for r in assessment.reasons[:5])}

**Questions**:
{questions_text}

Please review and provide answers to continue processing signals automatically.

---
*Run ID: {run_id[:8]}*"""

        need = await insert_need(
            workspace_id=self.workspace_id,
            customer_id=customer_id or "unknown",
            need_type=NeedType.SIDEKICK_QUESTION.value,
            headline=f"Review {len(low_confidence_signals)} signal(s) for routing",
            lede="Signal watcher paused - needs input to continue",
            agent_reasoning=reasoning,
            handbook_version_id=ctx.handbook_version_id,
            priority_rank=5,  # High priority
        )

        # Link need to agent run
        await self.dc.execute_mutation(
            "LinkNeedToAgentRun",
            {
                "needId": need["id"],
                "agentRunId": run_id,
            },
        )

        logger.info(
            "review_need_created",
            need_id=str(need["id"]),
            low_confidence_count=len(low_confidence_signals),
        )

        return str(need["id"])

    def _apply_answers(
        self,
        ctx: SignalWatcherContext,
        answers: dict[str, Any],
    ) -> SignalWatcherContext:
        """
        Apply human-provided answers to context.

        Updates signal routing based on user corrections.
        """
        # Process thread reassignments
        if "thread_reassignments" in answers:
            for signal_id, thread_id in answers["thread_reassignments"].items():
                if signal_id in ctx.thread_matches:
                    # Clear inferred match if user said "no"
                    if thread_id is None:
                        ctx.thread_matches[signal_id] = None
                    # Otherwise would update with user's choice (not implemented yet)

        # Process need reassignments
        if "need_reassignments" in answers:
            for signal_id, need_id in answers["need_reassignments"].items():
                if signal_id in ctx.need_matches:
                    if need_id is None:
                        ctx.need_matches[signal_id] = None

        # Process customer assignments
        if "customer_assignments" in answers:
            for signal_id, customer_id in answers["customer_assignments"].items():
                for signal in ctx.classified_signals:
                    if signal.id == signal_id:
                        signal.customer_id = customer_id
                        break

        logger.info(
            "answers_applied",
            thread_reassignments=len(answers.get("thread_reassignments", {})),
            need_reassignments=len(answers.get("need_reassignments", {})),
            customer_assignments=len(answers.get("customer_assignments", {})),
        )

        return ctx

"""
Loop Controller
State machine orchestrator for autonomous agent execution with pause/resume
"""

import asyncio
from datetime import datetime
from typing import Any
from uuid import uuid4

from google import genai

from config import settings
from core.logging import get_logger, bind_context, clear_context
from core.types import (
    AgentStatus,
    ConfidenceAssessment,
    ClarifyingQuestion,
    NotionDeal,
    NeedType,
    WorkspaceAgentSettings,
    AutonomyMode,
)
from core.errors import (
    PauseForInputSignal,
    AgentError,
    StepFailedError,
)
from db.dataconnect_client import get_dataconnect_client
from services.agent_run_service import AgentRunService
from services import get_integration_service
from tools.database_tool import get_handbook_version, insert_need

# NOTE: handoff_chain imports are done lazily inside methods to avoid circular import
# The circular import chain is:
#   routes/agents -> agents.handoff_chain.steps -> services -> setup_service
#   -> agents.handoff_auto.agent -> loop_controller -> agents.handoff_chain.steps
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from agents.handoff_chain.context import HandoffContext

from .confidence import assess_confidence, should_pause, merge_answers_into_deal


def _get_handoff_chain_steps():
    """Lazy import of handoff_chain steps to avoid circular import."""
    from agents.handoff_chain.steps import (
        read_deal_step,
        read_playbook_step,
        gap_analysis_step,
        write_handoff_brief_step,
        generate_plan_step,
        create_customer_step,
        surface_need_step,
    )
    return {
        'read_deal_step': read_deal_step,
        'read_playbook_step': read_playbook_step,
        'gap_analysis_step': gap_analysis_step,
        'write_handoff_brief_step': write_handoff_brief_step,
        'generate_plan_step': generate_plan_step,
        'create_customer_step': create_customer_step,
        'surface_need_step': surface_need_step,
    }


def _get_handoff_context_class():
    """Lazy import of HandoffContext to avoid circular import."""
    from agents.handoff_chain.context import HandoffContext
    return HandoffContext

logger = get_logger("LoopController")

# Step timeout in seconds
STEP_TIMEOUT = 60


class LoopController:
    """
    Orchestrates autonomous agent execution with confidence-aware pause/resume.

    Uses the existing handoff_chain steps but wraps them with:
    - State persistence for pause/resume
    - Confidence checking after key steps
    - Automatic resume when answers arrive
    """

    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id
        self.dc = get_dataconnect_client()
        self.run_service = AgentRunService(self.dc, workspace_id)
        from services import get_notion_service
        self.notion_service = get_notion_service(workspace_id)
        self.integration_service = get_integration_service(workspace_id)
        self._settings: WorkspaceAgentSettings | None = None

    async def _get_settings(self) -> WorkspaceAgentSettings | None:
        """Get agent settings for this workspace."""
        if self._settings is None:
            from db.dataconnect_client import get_dataconnect_client

            try:
                dc = get_dataconnect_client()
                result = await dc.execute_query(
                    "GetWorkspaceAgentSettings",
                    {
                        "workspaceId": self.workspace_id,
                        "agentName": "handoff_auto",
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
        notion_deal_id: str,
        trigger_type: str = "manual",
        triggered_by: str | None = None,
        settings_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Run the autonomous handoff agent for a specific deal.

        Args:
            notion_deal_id: Notion page ID of the deal
            trigger_type: How this run was triggered
            triggered_by: Who/what triggered it
            settings_override: Override workspace settings for this run

        Returns:
            Run result with status, IDs, and any pause information
        """
        # Create the run record
        run = await self.run_service.create_run(
            agent_name="handoff_auto",
            trigger_type=trigger_type,
            triggered_by=triggered_by,
            input_params={
                "notion_deal_id": notion_deal_id,
                "settings_override": settings_override,
            },
        )
        run_id = str(run["id"])

        # Bind logging context
        bind_context(
            run_id=run_id,
            workspace_id=self.workspace_id,
            agent="handoff_auto",
        )

        logger.info(
            "run_started",
            notion_deal_id=notion_deal_id,
            trigger_type=trigger_type,
        )

        try:
            # Start the run
            await self.run_service.start_run(run_id)

            # Execute the loop
            result = await self._execute_loop(
                run_id=run_id,
                notion_deal_id=notion_deal_id,
                settings_override=settings_override,
            )

            return result

        except PauseForInputSignal as pause:
            # Agent paused for input - this is expected control flow
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

    async def run_for_customer(
        self,
        customer_id: str,
        trigger_type: str = "setup_wizard",
        triggered_by: str | None = None,
        settings_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Run the autonomous handoff agent for an existing customer.

        This is used by the setup wizard to generate plans for imported customers
        who don't have a Notion deal (they're already customers).

        Args:
            customer_id: The existing customer UUID
            trigger_type: How this run was triggered
            triggered_by: Who/what triggered it
            settings_override: Override workspace settings for this run

        Returns:
            Run result with status, IDs, and any pause information
        """
        # Create the run record
        run = await self.run_service.create_run(
            agent_name="handoff_auto",
            trigger_type=trigger_type,
            triggered_by=triggered_by,
            input_params={
                "customer_id": customer_id,
                "settings_override": settings_override,
            },
        )
        run_id = str(run["id"])

        # Bind logging context
        bind_context(
            run_id=run_id,
            workspace_id=self.workspace_id,
            agent="handoff_auto",
        )

        logger.info(
            "run_started_for_customer",
            customer_id=customer_id,
            trigger_type=trigger_type,
        )

        try:
            # Start the run
            await self.run_service.start_run(run_id)

            # Execute the loop for existing customer
            result = await self._execute_loop_for_customer(
                run_id=run_id,
                customer_id=customer_id,
                settings_override=settings_override,
            )

            return result

        except PauseForInputSignal as pause:
            # Agent paused for input - this is expected control flow
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
            Run result with status and IDs
        """
        bind_context(
            run_id=run_id,
            workspace_id=self.workspace_id,
            agent="handoff_auto",
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
            notion_deal_id = run.get("input_params", {}).get("notion_deal_id")
            settings_override = run.get("input_params", {}).get("settings_override")

            # Transition to running
            await self.run_service.mark_running_after_resume(run_id)

            # Continue execution from where we paused
            # Note: DataConnect returns camelCase field names
            result = await self._execute_loop(
                run_id=run_id,
                notion_deal_id=notion_deal_id,
                settings_override=settings_override,
                context_snapshot=context_snapshot,
                resume_answers=answers,
                resume_from_step=run.get("currentStep"),  # camelCase from DataConnect
            )

            return result

        except PauseForInputSignal as pause:
            # Paused again (possible with multiple questions)
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
        notion_deal_id: str,
        settings_override: dict[str, Any] | None = None,
        context_snapshot: dict[str, Any] | None = None,
        resume_answers: dict[str, Any] | None = None,
        resume_from_step: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute the main agent loop.

        This reuses the handoff_chain steps with confidence checking.
        """
        # Get workspace-specific settings (optional)
        workspace_settings = await self._get_settings()

        # Initialize or restore context
        HandoffContext = _get_handoff_context_class()
        if context_snapshot:
            try:
                ctx = HandoffContext.from_dict(context_snapshot)
                # Merge answers into deal data if resuming
                if resume_answers:
                    if ctx.deal_data:
                        # Merge answers into existing deal data
                        deal = NotionDeal(**ctx.deal_data)
                        updated_deal = merge_answers_into_deal(deal, resume_answers)
                        ctx = ctx.with_deal_data(updated_deal.model_dump())
                    else:
                        # Create deal data from answers (no Notion deal linked)
                        deal = NotionDeal(
                            page_id=None,
                            company_name=resume_answers.get("company_name", "Unknown"),
                            arr_cents=self._parse_arr(resume_answers.get("arr_cents")),
                            timeline=resume_answers.get("timeline"),
                            stakeholders=[{"name": resume_answers.get("stakeholders")}] if resume_answers.get("stakeholders") else [],
                        )
                        ctx = ctx.with_deal_data(deal.model_dump())
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
            ctx = HandoffContext(
                workspace_id=self.workspace_id,
                notion_deal_id=notion_deal_id,
            )

        # Get handbook version
        handbook_version = await get_handbook_version(self.workspace_id)
        if handbook_version:
            ctx.handbook_version_id = handbook_version["id"]

        # Initialize GenAI client
        genai_client = genai.Client(api_key=settings.gemini_api_key)

        # Define step sequence
        # NOTE: create_customer must come BEFORE confidence_check so that
        # if the agent pauses for questions, there's a customer to attach the Need to
        steps = [
            ("read_deal", self._step_read_deal),
            ("read_playbook", self._step_read_playbook),
            ("create_customer", self._step_create_customer),  # Create customer first!
            ("confidence_check", self._step_confidence_check),  # Now questions can link to customer
            ("gap_analysis", self._step_gap_analysis),
            ("write_handoff_brief", self._step_write_handoff_brief),
            ("generate_plan", self._step_generate_plan),
            ("surface_need", self._step_surface_need),
        ]

        # Find starting step
        start_index = 0
        if resume_from_step:
            for i, (name, _) in enumerate(steps):
                if name == resume_from_step:
                    # Resume FROM the paused step to re-validate with new answers
                    # Exception: if we paused at confidence_check, skip to next
                    # since answers were already merged into deal data
                    if name == "confidence_check":
                        start_index = i + 1  # Skip confidence check (already validated with answers)
                    else:
                        start_index = i  # Re-run the step with merged answers
                    break

        # Execute steps
        for i in range(start_index, len(steps)):
            step_name, step_fn = steps[i]

            await self.run_service.update_step(
                run_id,
                step_name,
                ctx.to_dict() if hasattr(ctx, "to_dict") else None,
            )

            try:
                ctx = await asyncio.wait_for(
                    step_fn(ctx, run_id, genai_client, workspace_settings),
                    timeout=STEP_TIMEOUT,
                )
            except asyncio.TimeoutError:
                raise StepFailedError(
                    f"Step timed out after {STEP_TIMEOUT}s",
                    step_name=step_name,
                )

        # Complete the run
        result = {
            "customer_id": ctx.customer_id,
            "brief_id": str(ctx.handoff_brief["id"]) if ctx.handoff_brief else None,
            "plan_id": str(ctx.ai_plan["id"]) if ctx.ai_plan else None,
            "need_id": str(ctx.need["id"]) if ctx.need else None,
            "company_name": ctx.company_name,
        }

        await self.run_service.complete_run(
            run_id=run_id,
            result=result,
            customer_id=ctx.customer_id,
            brief_id=str(ctx.handoff_brief["id"]) if ctx.handoff_brief else None,
            plan_id=str(ctx.ai_plan["id"]) if ctx.ai_plan else None,
        )

        # Mark deal as processed
        await self.notion_service.mark_deal_processed(
            notion_deal_id=notion_deal_id,
            agent_run_id=run_id,
            customer_id=ctx.customer_id,
            brief_id=str(ctx.handoff_brief["id"]) if ctx.handoff_brief else None,
        )

        logger.info(
            "run_completed",
            run_id=run_id,
            customer_id=ctx.customer_id,
        )

        return {
            "run_id": run_id,
            "status": AgentStatus.COMPLETED.value,
            **result,
        }

    async def _execute_loop_for_customer(
        self,
        run_id: str,
        customer_id: str,
        settings_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute the agent loop for an existing customer (setup wizard flow).

        This is a simplified version that skips deal reading and customer creation.
        """
        # Lazy import to avoid circular dependency
        HandoffContext = _get_handoff_context_class()

        # Get workspace-specific settings (optional)
        workspace_settings = await self._get_settings()

        # Look up the existing customer using DataConnect
        customer = await self.dc.get_customer(customer_id)

        logger.info(
            "customer_lookup_result",
            customer_id=customer_id,
            found=customer is not None,
            customer_workspace_id=customer.get("workspace", {}).get("id") if customer else None,
            expected_workspace_id=self.workspace_id,
        )

        if not customer or customer.get("workspace", {}).get("id") != self.workspace_id:
            raise AgentError(
                f"Customer not found: {customer_id}",
                code="CUSTOMER_NOT_FOUND",
            )

        # Create context with customer data (converted to deal-like structure)
        # Note: DataConnect returns camelCase field names
        arr_cents_raw = customer.get("arrCents")
        arr_cents = int(arr_cents_raw) if arr_cents_raw is not None else None

        deal_data = {
            "page_id": customer.get("externalId") or customer_id,
            "company_name": customer["name"],
            "one_liner": customer.get("oneLiner"),
            "tier": customer.get("tier"),
            "arr_cents": arr_cents,
            # For existing customers, we don't have detailed deal data
            # The plan generation will use defaults and playbook
        }

        ctx = HandoffContext(
            workspace_id=self.workspace_id,
            notion_deal_id=customer.get("externalId") or customer_id,
            customer_id=customer_id,
            deal_data=deal_data,
        )

        # Get handbook version
        handbook_version = await get_handbook_version(self.workspace_id)
        if handbook_version:
            ctx.handbook_version_id = handbook_version["id"]

        # Initialize GenAI client
        genai_client = genai.Client(api_key=settings.gemini_api_key)

        # For existing customers, skip deal reading and customer creation
        # Steps: playbook selection -> plan generation -> surface need
        steps = [
            ("read_playbook", self._step_read_playbook),
            ("generate_plan", self._step_generate_plan),
            ("surface_need", self._step_surface_need_for_existing),
        ]

        # Execute steps
        for step_name, step_fn in steps:
            await self.run_service.update_step(
                run_id,
                step_name,
                ctx.to_dict() if hasattr(ctx, "to_dict") else None,
            )

            try:
                ctx = await asyncio.wait_for(
                    step_fn(ctx, run_id, genai_client, workspace_settings),
                    timeout=STEP_TIMEOUT,
                )
            except asyncio.TimeoutError:
                raise StepFailedError(
                    f"Step timed out after {STEP_TIMEOUT}s",
                    step_name=step_name,
                )

        # Complete the run
        result = {
            "customer_id": ctx.customer_id,
            "brief_id": None,  # No handoff brief for existing customers
            "plan_id": str(ctx.ai_plan["id"]) if ctx.ai_plan else None,
            "need_id": str(ctx.need["id"]) if ctx.need else None,
            "company_name": ctx.company_name,
        }

        await self.run_service.complete_run(
            run_id=run_id,
            result=result,
            customer_id=ctx.customer_id,
            brief_id=None,
            plan_id=str(ctx.ai_plan["id"]) if ctx.ai_plan else None,
        )

        logger.info(
            "run_completed_for_customer",
            run_id=run_id,
            customer_id=ctx.customer_id,
        )

        return {
            "run_id": run_id,
            "status": AgentStatus.COMPLETED.value,
            **result,
        }

    # =========================================================================
    # Step Wrappers
    # =========================================================================

    async def _step_read_deal(
        self,
        ctx: "HandoffContext",
        run_id: str,
        genai_client: genai.Client,
        settings: WorkspaceAgentSettings | None,
    ) -> "HandoffContext":
        """Wrap read_deal_step from handoff_chain."""
        steps = _get_handoff_chain_steps()
        return await steps['read_deal_step'](ctx)

    async def _step_read_playbook(
        self,
        ctx: "HandoffContext",
        run_id: str,
        genai_client: genai.Client,
        settings: WorkspaceAgentSettings | None,
    ) -> "HandoffContext":
        """Wrap read_playbook_step from handoff_chain."""
        steps = _get_handoff_chain_steps()
        return await steps['read_playbook_step'](ctx)

    async def _step_confidence_check(
        self,
        ctx: "HandoffContext",
        run_id: str,
        genai_client: genai.Client,
        settings: WorkspaceAgentSettings | None,
    ) -> "HandoffContext":
        """
        Check confidence and pause if needed.
        This is our key addition to the handoff_chain flow.
        """
        # Build NotionDeal from context
        deal_data = ctx.deal_data or {}
        deal = NotionDeal(
            page_id=ctx.notion_deal_id,
            company_name=deal_data.get("company_name", "Unknown"),
            arr_cents=deal_data.get("arr_cents"),
            timeline=deal_data.get("timeline"),
            sales_commitments=deal_data.get("sales_commitments", []),
            technical_context=deal_data.get("technical_context", []),
            stakeholders=deal_data.get("stakeholders", []),
        )

        # Assess confidence
        assessment = assess_confidence(
            deal=deal,
            playbook=ctx.playbook,
            gap_analysis=None,  # Not available yet
        )

        # Check if we should pause
        if should_pause(assessment, settings):
            # Only create a Need if we have a customer_id (Needs require a customer)
            need_id = None
            if ctx.customer_id:
                need_id = await self._create_clarification_need(
                    ctx=ctx,
                    run_id=run_id,
                    assessment=assessment,
                )
            else:
                logger.info(
                    "skipping_need_creation_no_customer",
                    run_id=run_id,
                    reason="Cannot create Need without customer_id - questions stored in AgentRun",
                )

            # Save context for resume
            context_snapshot = self._serialize_context(ctx)

            # Pause the run - questions are stored in AgentRun.clarifyingQuestions
            await self.run_service.pause_for_input(
                run_id=run_id,
                confidence=assessment,
                questions=assessment.questions or [],
                blocking_need_id=need_id,  # May be None if no customer yet
                context_snapshot=context_snapshot,
            )

            # Raise signal to stop execution
            raise PauseForInputSignal(
                need_id=need_id,  # May be None
                questions=[q.model_dump() for q in (assessment.questions or [])],
                context=context_snapshot,
                run_id=run_id,
            )

        # Continue if confident
        logger.info(
            "confidence_check_passed",
            level=assessment.level.value,
            score=assessment.score,
        )

        return ctx

    async def _step_gap_analysis(
        self,
        ctx: "HandoffContext",
        run_id: str,
        genai_client: genai.Client,
        settings: WorkspaceAgentSettings | None,
    ) -> "HandoffContext":
        """Wrap gap_analysis_step from handoff_chain."""
        steps = _get_handoff_chain_steps()
        return await steps['gap_analysis_step'](ctx, genai_client)

    async def _step_write_handoff_brief(
        self,
        ctx: "HandoffContext",
        run_id: str,
        genai_client: genai.Client,
        settings: WorkspaceAgentSettings | None,
    ) -> "HandoffContext":
        """Wrap write_handoff_brief_step from handoff_chain."""
        steps = _get_handoff_chain_steps()
        return await steps['write_handoff_brief_step'](ctx)

    async def _step_generate_plan(
        self,
        ctx: "HandoffContext",
        run_id: str,
        genai_client: genai.Client,
        settings: WorkspaceAgentSettings | None,
    ) -> "HandoffContext":
        """Wrap generate_plan_step from handoff_chain."""
        steps = _get_handoff_chain_steps()
        return await steps['generate_plan_step'](ctx, genai_client)

    async def _step_create_customer(
        self,
        ctx: "HandoffContext",
        run_id: str,
        genai_client: genai.Client,
        settings: WorkspaceAgentSettings | None,
    ) -> "HandoffContext":
        """Wrap create_customer_step from handoff_chain."""
        steps = _get_handoff_chain_steps()
        return await steps['create_customer_step'](ctx)

    async def _step_surface_need(
        self,
        ctx: "HandoffContext",
        run_id: str,
        genai_client: genai.Client,
        settings: WorkspaceAgentSettings | None,
    ) -> "HandoffContext":
        """Wrap surface_need_step from handoff_chain."""
        steps = _get_handoff_chain_steps()
        return await steps['surface_need_step'](ctx)

    async def _step_surface_need_for_existing(
        self,
        ctx: "HandoffContext",
        run_id: str,
        genai_client: genai.Client,
        settings: WorkspaceAgentSettings | None,
    ) -> "HandoffContext":
        """Create a need for reviewing onboarding plan for existing customer."""
        # Create a need for plan approval
        milestone_count = len(ctx.ai_plan.get("milestones", [])) if ctx.ai_plan else 0

        playbook_name = ctx.playbook.get('name', 'default') if ctx.playbook else 'default'
        need = await insert_need(
            workspace_id=self.workspace_id,
            customer_id=ctx.customer_id,
            need_type=NeedType.PLAN_APPROVAL_REQUIRED.value,
            headline=f"Review onboarding plan for {ctx.company_name}",
            lede=f"AI generated {milestone_count} milestones based on {playbook_name} playbook",
            agent_reasoning=f"Customer was added via setup wizard. Generated onboarding plan requires review before activation.",
            priority_rank=5,  # High priority for review (lower = higher)
        )

        ctx = ctx.with_need(need)

        logger.info(
            "need_surfaced_for_existing_customer",
            need_id=str(need["id"]),
            customer_id=ctx.customer_id,
        )

        return ctx

    # =========================================================================
    # Helpers
    # =========================================================================

    async def _create_clarification_need(
        self,
        ctx: "HandoffContext",
        run_id: str,
        assessment: ConfidenceAssessment,
    ) -> str:
        """Create a need in Today Queue for user to answer clarifying questions."""
        questions = assessment.questions or []

        # Format questions for display
        questions_text = "\n".join(
            f"**{i+1}. {q.question}**\n   _{q.context or ''}_"
            for i, q in enumerate(questions)
        )

        reasoning = f"""The autonomous handoff agent needs clarification before proceeding.

**Confidence Level**: {assessment.level.value.upper()} ({assessment.score:.0%})

**Reasons for pause**:
{chr(10).join(f'- {r}' for r in assessment.reasons)}

**Questions**:
{questions_text}

Please provide answers to continue processing this handoff automatically.

---
*Run ID: {run_id[:8]}*"""

        need = await insert_need(
            workspace_id=self.workspace_id,
            customer_id=ctx.customer_id or "pending",  # May not have customer yet
            need_type=NeedType.UNCATEGORIZED.value,
            headline=f"Clarify {len(questions)} question(s) for {ctx.company_name} handoff",
            lede="Agent paused - needs input to continue",
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
            "clarification_need_created",
            need_id=str(need["id"]),
            question_count=len(questions),
        )

        return str(need["id"])

    def _serialize_context(self, ctx: "HandoffContext") -> dict[str, Any]:
        """Serialize context for storage and resume."""
        return {
            "workspace_id": ctx.workspace_id,
            "notion_deal_id": ctx.notion_deal_id,
            "customer_id": ctx.customer_id,
            "run_id": ctx.run_id,
            "handbook_version_id": ctx.handbook_version_id,
            "deal_data": ctx.deal_data,
            "playbook": ctx.playbook,
            "playbook_milestones": ctx.playbook_milestones,
            "gap_analysis": ctx.gap_analysis,
            "handoff_brief": ctx.handoff_brief,
            "ai_plan": ctx.ai_plan,
            "customer": ctx.customer,
            "need": ctx.need,
            "errors": ctx.errors,
        }

    def _parse_arr(self, value: Any) -> int | None:
        """Parse ARR value from answer (handles formatted strings and numbers)."""
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value * 100)  # Assume dollars, convert to cents
        if isinstance(value, str):
            import re
            # Remove currency symbols, commas, and whitespace
            clean = re.sub(r"[^\d.]", "", value)
            if clean:
                try:
                    # If it looks like dollars, convert to cents
                    amount = float(clean)
                    if amount < 1_000_000:  # Likely dollars
                        return int(amount * 100)
                    return int(amount)  # Already in cents
                except ValueError:
                    return None
        return None

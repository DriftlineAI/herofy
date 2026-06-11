"""
HandoffChain Steps
Individual step implementations for the sequential agent

These steps are orchestrated by the HandoffChainAgent to process
new deal handoffs. Each step is an async function that takes a
HandoffContext and returns an updated context.

The agent uses Google GenAI SDK (google-genai) for LLM calls
during gap analysis and plan generation.

Features:
- Retry logic for LLM calls (exponential backoff)
- Output validation via Pydantic models
- OpenTelemetry tracing for observability
- Transaction management for multi-write operations
"""

import json
from typing import Any

from google import genai

from core.errors import StepFailedError
from core.logging import get_logger
from core.retry import retry_with_backoff
from core.metrics import trace_step, trace_llm_call
from core.validation import validate_output
from core.transactions import critical_transaction
from core.model_config import get_model, ModelUseCase
from services import get_customer_service, get_handoff_service, get_plan_service
from tools.notion_tool import read_notion_deal
from tools.database_tool import (
    get_playbook,
    get_playbook_milestones,
    get_handbook_version,
    insert_need,
    update_handoff_brief_customer,
)

from .context import HandoffContext
from .prompts import GAP_ANALYSIS_PROMPT, PLAN_GENERATION_PROMPT, NEED_REASONING_TEMPLATE
from .validation_models import GapAnalysisOutput, PlanGenerationOutput

logger = get_logger("HandoffChainSteps")


# =============================================================================
# Step 1: Read Deal from Notion
# =============================================================================


async def read_deal_step(ctx: HandoffContext) -> HandoffContext:
    """
    Step 1: Read the Notion deal page and extract structured data.

    Args:
        ctx: Current handoff context

    Returns:
        Updated context with deal_data populated
    """
    logger.info(
        "step_started",
        step="ReadDealStep",
        run_id=ctx.run_id,
        notion_deal_id=ctx.notion_deal_id,
    )

    # If no notion_deal_id, skip this step and use minimal context
    if not ctx.notion_deal_id:
        logger.warning(
            "step_skipped_no_deal_id",
            step="ReadDealStep",
            run_id=ctx.run_id,
        )
        # Return context with empty deal data - agent will work with customer data instead
        return ctx.with_deal_data({
            "company_name": "Unknown",  # Will be populated from customer data later
            "notes": "No Notion deal linked - using customer data only",
        })

    try:
        # Pass workspace_id so read_notion_deal can get OAuth token
        deal_data = await read_notion_deal(
            deal_id=ctx.notion_deal_id,
            workspace_id=ctx.workspace_id,
        )

        if "error" in deal_data:
            raise StepFailedError(
                f"Failed to read Notion deal: {deal_data['error']}",
                step_name="ReadDealStep",
            )

        logger.info(
            "step_completed",
            step="ReadDealStep",
            run_id=ctx.run_id,
            company_name=deal_data.get("company_name"),
        )

        return ctx.with_deal_data(deal_data)

    except StepFailedError:
        raise
    except Exception as e:
        logger.error("step_failed", step="ReadDealStep", error=str(e))
        raise StepFailedError(str(e), step_name="ReadDealStep")


# =============================================================================
# Step 2: Read Playbook
# =============================================================================


async def read_playbook_step(ctx: HandoffContext) -> HandoffContext:
    """
    Step 2: Fetch the best-fit playbook from the database.

    Args:
        ctx: Current handoff context with deal_data

    Returns:
        Updated context with playbook and playbook_milestones
    """
    logger.info(
        "step_started",
        step="ReadPlaybookStep",
        run_id=ctx.run_id,
    )

    try:
        arr_cents = ctx.deal_data.get("arr_cents") if ctx.deal_data else None
        playbook = await get_playbook(ctx.workspace_id, arr_cents)

        if "error" in playbook:
            raise StepFailedError(
                f"No playbook found: {playbook['error']}",
                step_name="ReadPlaybookStep",
            )

        # Validate playbook has required fields
        if "id" not in playbook:
            raise StepFailedError(
                "Playbook missing required 'id' field",
                step_name="ReadPlaybookStep",
            )

        milestones = await get_playbook_milestones(playbook["id"], ctx.workspace_id)

        logger.info(
            "step_completed",
            step="ReadPlaybookStep",
            run_id=ctx.run_id,
            playbook_name=playbook["name"],
            milestone_count=len(milestones),
        )

        return ctx.with_playbook(playbook, milestones)

    except StepFailedError:
        raise
    except Exception as e:
        logger.error("step_failed", step="ReadPlaybookStep", error=str(e))
        raise StepFailedError(str(e), step_name="ReadPlaybookStep")


# =============================================================================
# Step 3: Gap Analysis (LLM)
# =============================================================================


@retry_with_backoff(max_attempts=3, base_delay=1.0, max_delay=10.0)
@trace_llm_call("gap_analysis")
async def _call_llm_for_gap_analysis(
    prompt: str,
    client: genai.Client,
) -> str:
    """
    Isolated LLM call for gap analysis with retry and tracing.

    Args:
        prompt: The gap analysis prompt
        client: Configured GenAI client

    Returns:
        Raw response text from LLM
    """
    model_name = get_model(ModelUseCase.GAP_ANALYSIS)
    response = await client.aio.models.generate_content(
        model=model_name,
        contents=prompt,
    )
    return response.text.strip()


@trace_step("GapAnalysisStep")
@validate_output(GapAnalysisOutput, extract_field="gap_analysis")
async def gap_analysis_step(
    ctx: HandoffContext,
    client: genai.Client,
) -> HandoffContext:
    """
    Step 3: Use LLM to analyze gaps between commitments and playbook.

    Features:
    - Retry logic for transient LLM failures (3 attempts, exponential backoff)
    - Output validation against GapAnalysisOutput schema
    - OpenTelemetry tracing for observability

    Args:
        ctx: Current handoff context
        client: Configured GenAI client for analysis

    Returns:
        Updated context with gap_analysis
    """
    logger.info(
        "step_started",
        step="GapAnalysisStep",
        run_id=ctx.run_id,
    )

    try:
        # Build prompt from context
        prompt = _build_gap_analysis_prompt(ctx)

        # Call LLM with retry logic
        response_text = await _call_llm_for_gap_analysis(prompt, client)

        # Parse JSON response - extract first JSON block
        gap_analysis = _extract_json_from_llm_response(response_text)

        logger.info(
            "step_completed",
            step="GapAnalysisStep",
            run_id=ctx.run_id,
            confidence=gap_analysis.get("confidence"),
            risk_count=len(gap_analysis.get("risks", [])),
        )

        return ctx.with_gap_analysis(gap_analysis)

    except json.JSONDecodeError as e:
        logger.error("step_failed", step="GapAnalysisStep", error=f"JSON parse error: {e}")
        # Provide default gap analysis on parse failure
        default_analysis = {
            "confidence": "low",
            "timeline_feasible": True,
            "risks": ["Unable to complete automated gap analysis - manual review recommended"],
            "recommendations": ["Review deal context manually"],
            "open_questions": [],
        }
        return ctx.with_gap_analysis(default_analysis)

    except Exception as e:
        logger.error("step_failed", step="GapAnalysisStep", error=str(e))
        raise StepFailedError(str(e), step_name="GapAnalysisStep")


def _build_gap_analysis_prompt(ctx: HandoffContext) -> str:
    """Build the gap analysis prompt from context."""
    deal = ctx.deal_data or {}
    playbook = ctx.playbook or {}
    milestones = ctx.playbook_milestones or []

    # Format commitments
    commitments = deal.get("sales_commitments", [])
    commitments_list = "\n".join(
        f"- {c.get('item', c)}: {c.get('details', '')}"
        for c in commitments
    ) or "No specific commitments recorded"

    # Format technical requirements
    technical = deal.get("technical_context", [])
    technical_list = "\n".join(
        f"- {t.get('item', t)}: {t.get('details', '')}"
        for t in technical
    ) or "No specific technical requirements"

    # Format milestones
    milestones_list = "\n".join(
        f"- {m['title']} ({m.get('owner_side', 'joint')}, {m.get('duration_days', 7)} days)"
        for m in milestones
    ) or "No milestones defined"

    # Format notes context (truncate if too long)
    notes_raw = deal.get("notes", "") or ""
    if len(notes_raw) > 5000:
        notes_context = notes_raw[:5000] + "\n... [truncated]"
    else:
        notes_context = notes_raw if notes_raw else "No additional notes available"

    # Calculate total playbook duration (sum of all milestone durations)
    playbook_duration = sum(
        m.get("duration_days", 7) for m in milestones
    ) or 45

    arr_cents = deal.get("arr_cents", 0)
    arr_display = f"{arr_cents / 100:,.0f}" if arr_cents else "Unknown"

    return GAP_ANALYSIS_PROMPT.format(
        company_name=deal.get("company_name", "Unknown"),
        arr_display=arr_display,
        timeline=deal.get("timeline", "Not specified"),
        commitments_list=commitments_list,
        technical_list=technical_list,
        notes_context=notes_context,
        playbook_name=playbook.get("name", "Standard"),
        playbook_archetype=playbook.get("archetype", "Unknown"),
        playbook_duration=playbook_duration,
        milestone_count=len(milestones),
        milestones_list=milestones_list,
    )


# =============================================================================
# Step 4: Write Handoff Brief
# =============================================================================


async def write_handoff_brief_step(ctx: HandoffContext) -> HandoffContext:
    """
    Step 4: Create the handoff brief in the database.

    Args:
        ctx: Current handoff context

    Returns:
        Updated context with handoff_brief
    """
    logger.info(
        "step_started",
        step="WriteHandoffBriefStep",
        run_id=ctx.run_id,
    )

    try:
        service = get_handoff_service(ctx.workspace_id)

        brief = await service.create_brief(
            deal_data=ctx.deal_data,
            gap_analysis=ctx.gap_analysis,
            handbook_version_id=ctx.handbook_version_id,
            customer_id=ctx.customer_id,
            notion_deal_id=ctx.notion_deal_id,
        )

        logger.info(
            "step_completed",
            step="WriteHandoffBriefStep",
            run_id=ctx.run_id,
            brief_id=str(brief["id"]),
        )

        return ctx.with_handoff_brief(brief)

    except Exception as e:
        logger.error("step_failed", step="WriteHandoffBriefStep", error=str(e))
        raise StepFailedError(str(e), step_name="WriteHandoffBriefStep")


# =============================================================================
# Step 5: Generate Plan (LLM)
# =============================================================================


@retry_with_backoff(max_attempts=3, base_delay=1.0, max_delay=10.0)
@trace_llm_call("plan_generation")
async def _call_llm_for_plan_generation(
    prompt: str,
    client: genai.Client,
) -> str:
    """
    Isolated LLM call for plan generation with retry and tracing.

    Args:
        prompt: The plan generation prompt
        client: Configured GenAI client

    Returns:
        Raw response text from LLM
    """
    model_name = get_model(ModelUseCase.PLAN_GENERATION)
    response = await client.aio.models.generate_content(
        model=model_name,
        contents=prompt,
    )
    return response.text.strip()


@trace_step("GeneratePlanStep")
async def generate_plan_step(
    ctx: HandoffContext,
    client: genai.Client,
) -> HandoffContext:
    """
    Step 5: Use LLM to generate an onboarding plan.

    Features:
    - Retry logic for transient LLM failures (3 attempts, exponential backoff)
    - OpenTelemetry tracing for observability
    - Fallback to adapted playbook milestones on parse failure

    Args:
        ctx: Current handoff context
        client: Configured GenAI client

    Returns:
        Updated context with ai_plan
    """
    logger.info(
        "step_started",
        step="GeneratePlanStep",
        run_id=ctx.run_id,
    )

    try:
        # Build prompt
        prompt = _build_plan_generation_prompt(ctx)

        # Call LLM with retry logic
        response_text = await _call_llm_for_plan_generation(prompt, client)

        # Parse JSON response - extract first JSON block
        plan_data = _extract_json_from_llm_response(response_text)

        # Create plan in database
        service = get_plan_service(ctx.workspace_id)

        # brief_id is optional for existing customers
        brief_id = str(ctx.handoff_brief["id"]) if ctx.handoff_brief else None

        plan = await service.create_plan(
            brief_id=brief_id,
            customer_id=ctx.customer_id,
            playbook=ctx.playbook,
            milestones=plan_data.get("milestones", []),
            headline=plan_data.get("headline", "Onboarding plan generated"),
            rationale=plan_data.get("rationale", ""),
            handbook_version_id=ctx.handbook_version_id,
        )

        logger.info(
            "step_completed",
            step="GeneratePlanStep",
            run_id=ctx.run_id,
            plan_id=str(plan["id"]),
            milestone_count=plan.get("milestone_count", 0),
        )

        return ctx.with_ai_plan(plan)

    except json.JSONDecodeError as e:
        logger.error("step_failed", step="GeneratePlanStep", error=f"JSON parse error: {e}")
        # Create plan from playbook milestones as fallback
        service = get_plan_service(ctx.workspace_id)

        adapted_milestones = await service.adapt_milestones(
            ctx.playbook_milestones or [],
            ctx.deal_data or {},
            ctx.gap_analysis or {},
        )

        # brief_id is optional for existing customers
        brief_id = str(ctx.handoff_brief["id"]) if ctx.handoff_brief else None

        plan = await service.create_plan(
            brief_id=brief_id,
            customer_id=ctx.customer_id,
            playbook=ctx.playbook,
            milestones=adapted_milestones,
            headline="Standard onboarding plan (auto-generated)",
            rationale="Adapted from playbook template due to LLM response parsing failure.",
            handbook_version_id=ctx.handbook_version_id,
        )

        return ctx.with_ai_plan(plan)

    except Exception as e:
        logger.error("step_failed", step="GeneratePlanStep", error=str(e))
        raise StepFailedError(str(e), step_name="GeneratePlanStep")


def _build_plan_generation_prompt(ctx: HandoffContext) -> str:
    """Build the plan generation prompt from context."""
    deal = ctx.deal_data or {}
    playbook = ctx.playbook or {}
    milestones = ctx.playbook_milestones or []
    gap = ctx.gap_analysis or {}

    # Format commitments
    commitments = deal.get("sales_commitments", [])
    commitments_list = "\n".join(
        f"- {c.get('item', c)}: {c.get('details', '')}"
        for c in commitments
    ) or "No specific commitments"

    # Format notes context (truncate if too long)
    notes_raw = deal.get("notes", "") or ""
    if len(notes_raw) > 5000:
        notes_context = notes_raw[:5000] + "\n... [truncated]"
    else:
        notes_context = notes_raw if notes_raw else "No additional notes available"

    # Format risks
    risks = gap.get("risks", [])
    risks_list = "\n".join(f"- {r}" for r in risks) or "No significant risks identified"

    # Format milestones
    milestones_list = "\n".join(
        f"- {m['title']} ({m.get('owner_side', 'joint')}, {m.get('duration_days', 7)} days): {m.get('description', '')}"
        for m in milestones
    ) or "No template milestones"

    arr_cents = deal.get("arr_cents", 0)
    arr_display = f"{arr_cents / 100:,.0f}" if arr_cents else "Unknown"

    return PLAN_GENERATION_PROMPT.format(
        company_name=deal.get("company_name", "Unknown"),
        arr_display=arr_display,
        timeline=deal.get("timeline", "Not specified"),
        commitments_list=commitments_list,
        notes_context=notes_context,
        gap_confidence=gap.get("confidence", "medium"),
        timeline_feasible=gap.get("timeline_feasible", True),
        risks_list=risks_list,
        playbook_name=playbook.get("name", "Standard"),
        milestones_list=milestones_list,
    )


# =============================================================================
# Step 6: Create Customer
# =============================================================================


async def create_customer_step(ctx: HandoffContext) -> HandoffContext:
    """
    Step 6: Create or find the customer record.

    Args:
        ctx: Current handoff context

    Returns:
        Updated context with customer
    """
    logger.info(
        "step_started",
        step="CreateCustomerStep",
        run_id=ctx.run_id,
    )

    try:
        # If customer_id already provided, fetch existing
        if ctx.customer_id:
            service = get_customer_service(ctx.workspace_id)
            customer = await service.get_by_id(ctx.customer_id)

            if customer:
                logger.info(
                    "step_completed",
                    step="CreateCustomerStep",
                    run_id=ctx.run_id,
                    customer_id=ctx.customer_id,
                    action="existing",
                )
                return ctx.with_customer(customer)

        # Create new customer from deal data
        service = get_customer_service(ctx.workspace_id)
        customer = await service.create_from_deal(ctx.deal_data or {})

        # Link customer to brief and plan
        await update_handoff_brief_customer(
            str(ctx.handoff_brief["id"]),
            str(customer["id"]),
        )

        # Update plan with customer_id
        if ctx.ai_plan:
            plan_service = get_plan_service(ctx.workspace_id)
            await plan_service.link_customer(
                str(ctx.ai_plan["id"]),
                str(customer["id"]),
            )

        logger.info(
            "step_completed",
            step="CreateCustomerStep",
            run_id=ctx.run_id,
            customer_id=str(customer["id"]),
            action="created",
        )

        return ctx.with_customer(customer)

    except Exception as e:
        logger.error("step_failed", step="CreateCustomerStep", error=str(e))
        raise StepFailedError(str(e), step_name="CreateCustomerStep")


# =============================================================================
# Step 7: Surface Need
# =============================================================================


async def surface_need_step(ctx: HandoffContext) -> HandoffContext:
    """
    Step 7: Create a need in the Today queue.

    Args:
        ctx: Current handoff context

    Returns:
        Updated context with need
    """
    logger.info(
        "step_started",
        step="SurfaceNeedStep",
        run_id=ctx.run_id,
    )

    try:
        # Build agent reasoning
        agent_reasoning = _build_need_reasoning(ctx)

        need = await insert_need(
            workspace_id=ctx.workspace_id,
            customer_id=str(ctx.customer["id"]),
            need_type="plan_approval_required",
            headline=f"{ctx.company_name} onboarding plan ready for review",
            lede=f"Handoff brief and {ctx.playbook.get('name', 'onboarding')} plan generated",
            agent_reasoning=agent_reasoning,
            handbook_version_id=ctx.handbook_version_id,
            priority_rank=10,
        )

        logger.info(
            "step_completed",
            step="SurfaceNeedStep",
            run_id=ctx.run_id,
            need_id=str(need["id"]),
        )

        return ctx.with_need(need)

    except Exception as e:
        logger.error("step_failed", step="SurfaceNeedStep", error=str(e))
        raise StepFailedError(str(e), step_name="SurfaceNeedStep")


def _build_need_reasoning(ctx: HandoffContext) -> str:
    """Build the agent_reasoning field for the need."""
    deal = ctx.deal_data or {}
    gap = ctx.gap_analysis or {}
    plan = ctx.ai_plan or {}
    playbook = ctx.playbook or {}

    arr_cents = deal.get("arr_cents", 0)
    arr_display = f"{arr_cents / 100:,.0f}" if arr_cents else "Unknown"

    # Format risks summary
    risks = gap.get("risks", [])
    if risks:
        risks_summary = "Key risks identified:\n" + "\n".join(f"- {r}" for r in risks[:3])
    else:
        risks_summary = "No significant risks identified - standard handoff."

    return NEED_REASONING_TEMPLATE.format(
        company_name=ctx.company_name,
        arr_display=arr_display,
        notion_deal_id=ctx.notion_deal_id,
        brief_id=str(ctx.handoff_brief["id"]) if ctx.handoff_brief else "N/A",
        commitment_count=len(deal.get("sales_commitments", [])),
        technical_count=len(deal.get("technical_context", [])),
        confidence=gap.get("confidence", "medium"),
        plan_id=str(plan.get("id", "N/A")),
        playbook_name=playbook.get("name", "Standard"),
        milestone_count=plan.get("milestone_count", 0),
        duration=plan.get("duration_label", "unknown"),
        risks_summary=risks_summary,
    )


# =============================================================================
# Helper Functions
# =============================================================================


import re


def _extract_json_from_llm_response(response_text: str) -> dict[str, Any]:
    """
    Extract JSON from LLM response, handling various formats:
    - Raw JSON
    - JSON in markdown code blocks (```json ... ```)
    - JSON with surrounding text/explanation

    Args:
        response_text: Raw LLM response text

    Returns:
        Parsed JSON as dict

    Raises:
        json.JSONDecodeError: If no valid JSON found
    """
    text = response_text.strip()

    # Try 1: Direct JSON parse (clean response)
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # Try 2: Extract from markdown code block
    code_block_pattern = r"```(?:json)?\s*\n?([\s\S]*?)\n?```"
    matches = re.findall(code_block_pattern, text)
    if matches:
        # Try first code block (most likely to be the JSON)
        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue

    # Try 3: Find JSON object anywhere in text
    # Look for outermost {...} structure
    json_pattern = r"\{[\s\S]*\}"
    json_matches = re.findall(json_pattern, text)
    for match in json_matches:
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue

    # Nothing worked - raise the error with original text
    raise json.JSONDecodeError("No valid JSON found in response", text, 0)

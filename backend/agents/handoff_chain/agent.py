"""
HandoffChain Agent
Autonomous agent for processing new deal handoffs using Google ADK

This agent uses the Google Agent Development Kit (ADK) SequentialAgent pattern
to orchestrate 7 sequential steps for processing new deal handoffs.

See: https://google.github.io/adk-docs/agents/workflow-agents/sequential-agents/
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from google import genai

from config import settings
from core.errors import AgentError, AgentTimeoutError, StepFailedError
from core.logging import get_logger, bind_context, clear_context
from db.dataconnect_client import get_dataconnect_client
from tools.database_tool import get_handbook_version

from .context import HandoffContext
from .steps import (
    read_deal_step,
    read_playbook_step,
    gap_analysis_step,
    write_handoff_brief_step,
    generate_plan_step,
    create_customer_step,
    surface_need_step,
)

logger = get_logger("HandoffChainAgent")

# Step timeout in seconds
STEP_TIMEOUT = 60


@dataclass
class HandoffChainResult:
    """Result from HandoffChain agent execution."""

    run_id: str
    status: str  # "completed" | "failed"
    customer_id: str | None = None
    brief_id: str | None = None
    plan_id: str | None = None
    need_id: str | None = None
    error: str | None = None
    duration_ms: int | None = None


async def run_handoff_chain(
    workspace_id: str,
    notion_deal_id: str,
    customer_id: str | None = None,
) -> HandoffChainResult:
    """
    Run the HandoffChain agent to process a new deal.

    This is the main entry point for the HandoffChain agent.
    It orchestrates 7 sequential steps:
    1. ReadDealStep - Read Notion deal page
    2. ReadPlaybookStep - Fetch best-fit playbook
    3. GapAnalysisStep - Compare commitments vs playbook (LLM)
    4. WriteHandoffBriefStep - Insert handoff_briefs row
    5. GeneratePlanStep - Generate AI plan with milestones (LLM)
    6. CreateCustomerStep - Create/find customer
    7. SurfaceNeedStep - Surface need in Today queue

    Args:
        workspace_id: The workspace UUID
        notion_deal_id: Notion page ID for the deal
        customer_id: Optional existing customer UUID

    Returns:
        HandoffChainResult with status and created record IDs
    """
    start_time = datetime.utcnow()

    # Initialize context
    ctx = HandoffContext(
        workspace_id=workspace_id,
        notion_deal_id=notion_deal_id,
        customer_id=customer_id,
    )

    # Bind logging context
    bind_context(
        run_id=ctx.run_id,
        workspace_id=workspace_id,
        agent="HandoffChain",
    )

    logger.info(
        "agent_started",
        notion_deal_id=notion_deal_id,
        customer_id=customer_id,
    )

    try:
        # Get handbook version for audit trail (required for DB constraints)
        handbook_version = await get_handbook_version(workspace_id)
        if handbook_version:
            ctx.handbook_version_id = handbook_version["id"]
        else:
            # Create a default handbook version if none exists
            # This is required because handbookVersionId is NOT NULL in the schema
            handbook_version = await _ensure_handbook_version(workspace_id)
            ctx.handbook_version_id = handbook_version["id"]
            logger.info(
                "default_handbook_version_created",
                workspace_id=workspace_id,
                handbook_version_id=handbook_version["id"],
            )

        # Initialize Gemini client for LLM steps
        genai_client = genai.Client(api_key=settings.gemini_api_key)

        # Execute steps sequentially
        ctx = await _run_step_with_timeout(
            "ReadDealStep",
            lambda c: read_deal_step(c),
            ctx,
        )

        ctx = await _run_step_with_timeout(
            "ReadPlaybookStep",
            lambda c: read_playbook_step(c),
            ctx,
        )

        ctx = await _run_step_with_timeout(
            "GapAnalysisStep",
            lambda c: gap_analysis_step(c, genai_client),
            ctx,
        )

        ctx = await _run_step_with_timeout(
            "WriteHandoffBriefStep",
            lambda c: write_handoff_brief_step(c),
            ctx,
        )

        ctx = await _run_step_with_timeout(
            "GeneratePlanStep",
            lambda c: generate_plan_step(c, genai_client),
            ctx,
        )

        ctx = await _run_step_with_timeout(
            "CreateCustomerStep",
            lambda c: create_customer_step(c),
            ctx,
        )

        ctx = await _run_step_with_timeout(
            "SurfaceNeedStep",
            lambda c: surface_need_step(c),
            ctx,
        )

        # Calculate duration
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        logger.info(
            "agent_completed",
            duration_ms=duration_ms,
            customer_id=ctx.customer_id,
            brief_id=str(ctx.handoff_brief["id"]) if ctx.handoff_brief else None,
            plan_id=str(ctx.ai_plan["id"]) if ctx.ai_plan else None,
        )

        return HandoffChainResult(
            run_id=ctx.run_id,
            status="completed",
            customer_id=ctx.customer_id,
            brief_id=str(ctx.handoff_brief["id"]) if ctx.handoff_brief else None,
            plan_id=str(ctx.ai_plan["id"]) if ctx.ai_plan else None,
            need_id=str(ctx.need["id"]) if ctx.need else None,
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

        return HandoffChainResult(
            run_id=ctx.run_id,
            status="failed",
            customer_id=ctx.customer_id,
            brief_id=str(ctx.handoff_brief["id"]) if ctx.handoff_brief else None,
            plan_id=str(ctx.ai_plan["id"]) if ctx.ai_plan else None,
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

        return HandoffChainResult(
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
    ctx: HandoffContext,
) -> HandoffContext:
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


async def _ensure_handbook_version(workspace_id: str) -> dict[str, Any]:
    """
    Ensure a handbook version exists for the workspace.

    Creates a default handbook doc and version if none exists.
    This is required because handbookVersionId is NOT NULL in the schema.

    Args:
        workspace_id: The workspace UUID

    Returns:
        dict with 'id' of the handbook version
    """
    dc = get_dataconnect_client()

    # Check for existing handbook version
    result = await dc.execute_query("GetLatestHandbookVersion", {"workspaceId": workspace_id})
    versions = result.get("handbookVersions", [])

    if versions:
        return {"id": versions[0]["id"]}

    # No version exists - create default doc and version
    doc_result = await dc.execute_mutation(
        "CreateHandbookDoc",
        {
            "workspaceId": workspace_id,
            "slug": "default-handbook",
            "title": "Default Handbook",
            "description": "Auto-generated default handbook",
            "body": "# Default Handbook\n\nThis is a placeholder handbook created automatically.",
            "blastRadius": "low",
        },
    )

    doc = doc_result.get("handbookDoc_insert", {})
    doc_id = doc.get("id")
    logger.info("default_handbook_doc_created", doc_id=doc_id)

    # Create version
    version_result = await dc.execute_mutation(
        "CreateHandbookVersion",
        {
            "docId": doc_id,
            "body": "# Default Handbook\n\nThis is a placeholder handbook created automatically.",
        },
    )

    version = version_result.get("handbookVersion_insert", {})
    return {"id": version.get("id")}


async def _surface_error_need(ctx: HandoffContext, error: StepFailedError) -> None:
    """
    Surface an error as a need in the Today queue.

    This ensures CSMs are notified when handoff processing fails,
    even if the failure occurs before customer creation.
    """
    try:
        dc = get_dataconnect_client()

        # Ensure we have a handbook version (required for need creation)
        handbook_version_id = ctx.handbook_version_id
        if not handbook_version_id:
            handbook_version = await _ensure_handbook_version(ctx.workspace_id)
            handbook_version_id = handbook_version["id"]

        # Get customer_id, creating a placeholder if needed for early failures
        if ctx.customer_id:
            customer_id = ctx.customer_id
        elif ctx.customer:
            customer_id = str(ctx.customer["id"])
        else:
            # Early failure before customer creation - get or create placeholder
            customer_id = await _get_or_create_placeholder_customer(
                ctx.workspace_id,
                ctx.company_name or "Unknown (from deal)",
            )

        # Create error need using DataConnect
        await dc.execute_mutation(
            "CreateNeedWithId",
            {
                "workspaceId": ctx.workspace_id,
                "customerId": customer_id,
                "needType": "uncategorized",
                "headline": f"HandoffChain failed: {error.step_name}",
                "lede": f"Run ID: {ctx.run_id}",
                "agentReasoning": f"""HandoffChain agent failed during step: {error.step_name}

Error: {error.message}

What was attempted:
- Notion deal ID: {ctx.notion_deal_id}
- Company: {ctx.company_name or "Unknown"}

Please investigate and process this handoff manually if needed.""",
                "handbookVersionId": handbook_version_id,
                "priorityRank": 5,  # Higher priority for errors
                "workflowStatus": "needs_response",
            },
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


async def _get_or_create_placeholder_customer(
    workspace_id: str,
    company_name: str,
) -> str:
    """
    Get or create a placeholder customer for error tracking.

    Used when agent fails before customer creation to ensure
    errors can still be surfaced as needs.

    Args:
        workspace_id: The workspace UUID
        company_name: Company name from deal (may be empty)

    Returns:
        Customer UUID string
    """
    dc = get_dataconnect_client()

    # Generate a slug for the placeholder
    slug = f"agent-error-{company_name.lower().replace(' ', '-')[:30]}" if company_name else "agent-error-unknown"

    # Check if placeholder already exists (for same company name)
    result = await dc.execute_query(
        "GetCustomerBySlug",
        {
            "workspaceId": workspace_id,
            "slug": slug,
        },
    )

    existing = result.get("customer")
    if existing:
        return str(existing["id"])

    # Create placeholder customer
    customer_result = await dc.execute_mutation(
        "CreateCustomer",
        {
            "workspaceId": workspace_id,
            "name": company_name or "Unknown Customer",
            "slug": slug,
            "oneLiner": "Placeholder created for agent error tracking",
            "lifecycle": "handoff",
            "onboardingDayCurrent": 0,
        },
    )

    customer = customer_result.get("customer_insert", {})
    customer_id = str(customer.get("id"))

    logger.info(
        "placeholder_customer_created",
        customer_id=customer_id,
        slug=slug,
    )

    return customer_id

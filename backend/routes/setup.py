"""
Setup Routes
FastAPI endpoints for workspace setup completion
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from middleware.auth import FirebaseUser, require_workspace_access
from core.logging import get_logger
from db.dataconnect_client import get_dataconnect_client
from services.setup_service import SetupService

router = APIRouter(prefix="/setup", tags=["setup"])
logger = get_logger("setup_routes")


# =============================================================================
# Request/Response Models
# =============================================================================


class CompleteSetupRequest(BaseModel):
    """Request to complete workspace setup."""
    trigger_agents: bool = True  # Whether to trigger onboarding agents
    max_retries: int = Field(default=3, ge=0, le=10)  # Max retry attempts per customer (0-10)
    initial_backoff: int = Field(default=30, ge=1, le=300)  # Initial backoff in seconds (1-300)


class CompleteSetupResponse(BaseModel):
    """Response from setup completion."""
    success: bool
    message: str
    customers_analyzed: int
    agents_triggered: int
    agents_failed: int
    failed_customer_ids: list[str]
    sidekick_items_created: int


# =============================================================================
# Setup Completion Endpoint
# =============================================================================


@router.post("/{workspace_id}/complete")
async def complete_setup(
    workspace_id: str,
    request: CompleteSetupRequest,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> CompleteSetupResponse:
    """
    Complete workspace setup and trigger onboarding agents.

    This endpoint is called when the user finishes the setup wizard.
    It triggers the handoff_auto agent for all customers that need
    onboarding plans.

    **What it does:**
    1. Queries customers in 'onboarding' or 'handoff' lifecycle without plans
    2. Triggers handoff_auto agent for each customer
    3. Retries failed agents (3 attempts with exponential backoff: 30s, 60s, 120s)
    4. Creates sidekick items for customers that fail all retries

    **Note:** Agent execution happens in background. This endpoint returns
    immediately after triggering all agents. Users can track progress in
    the Today queue and Sidekick panel.

    Args:
        workspace_id: The workspace UUID
        request: Setup completion options
        user: Authenticated user (from Firebase)

    Returns:
        Summary of triggered agents and failures
    """
    logger.info(
        "setup_completion_requested",
        workspace_id=workspace_id,
        user_id=user.uid,
        trigger_agents=request.trigger_agents,
    )

    try:
        dc = get_dataconnect_client()
        setup_service = SetupService(dc, workspace_id)

        if not request.trigger_agents:
            # Skip agent triggering (e.g., for testing)
            logger.info(
                "setup_completion_skipped_agents",
                workspace_id=workspace_id,
            )
            return CompleteSetupResponse(
                success=True,
                message="Setup completed (agents skipped)",
                customers_analyzed=0,
                agents_triggered=0,
                agents_failed=0,
                failed_customer_ids=[],
                sidekick_items_created=0,
            )

        # First, run enrichment for all customers that were imported during setup
        # (enrichment was skipped during import to avoid slowing down the setup flow)
        # NOTE: We await enrichment before triggering agents so agents have goals/signals
        try:
            from services.enrichment_service import process_enrichment_queue
            logger.info(
                "setup_enrichment_started",
                workspace_id=workspace_id,
            )
            await process_enrichment_queue(workspace_id)
            logger.info(
                "setup_enrichment_completed",
                workspace_id=workspace_id,
            )
        except Exception as e:
            logger.warning(
                "setup_enrichment_failed",
                workspace_id=workspace_id,
                error=str(e),
            )
            # Don't fail setup if enrichment fails - agents can still work with raw_notes

        # Trigger agents synchronously with retry logic
        # NOTE: We await here rather than using background_tasks because
        # we want the retry logic to complete before returning the summary.
        # The actual agent execution still happens in background (agents
        # return immediately with run_id).
        #
        # TODO: For workspaces with many customers (50+), this could exceed
        # HTTP timeout (30-60s). Consider switching to background task with
        # progress tracking endpoint or SSE for large workspaces.
        results = await setup_service.trigger_onboarding_agents(
            max_retries=request.max_retries,
            initial_backoff=request.initial_backoff,
        )

        logger.info(
            "setup_completion_finished",
            workspace_id=workspace_id,
            **results,
        )

        # Build response message
        if results["agents_failed"] == 0:
            message = f"Setup complete! Triggered {results['agents_triggered']} onboarding agents."
        else:
            message = (
                f"Setup complete! Triggered {results['agents_triggered']} agents, "
                f"{results['agents_failed']} failed (see Sidekick for details)."
            )

        return CompleteSetupResponse(
            success=True,
            message=message,
            customers_analyzed=results["customers_analyzed"],
            agents_triggered=results["agents_triggered"],
            agents_failed=results["agents_failed"],
            failed_customer_ids=results["failed_customer_ids"],
            sidekick_items_created=results["sidekick_items_created"],
        )

    except Exception as e:
        logger.error(
            "setup_completion_failed",
            workspace_id=workspace_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Setup completion failed: {str(e)}",
        )

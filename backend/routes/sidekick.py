"""
Sidekick Routes
FastAPI endpoints for Sidekick items - HITL questions, tips, and agent progress.

These routes complement the DataConnect queries/mutations. Only use these endpoints
when you need:
1. AI logic (e.g., generating contextual tips)
2. Complex business logic (e.g., triggering agent resume after resolving a question)
3. Aggregation across resources

For simple CRUD, use DataConnect queries/mutations directly from the frontend.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from middleware.auth import FirebaseUser, require_workspace_access
from core.logging import get_logger
from db.dataconnect_client import get_dataconnect_client
from services.sidekick_service import SidekickService
from services.agent_run_service import AgentRunService

router = APIRouter(prefix="/workspaces", tags=["sidekick"])
logger = get_logger("sidekick_routes")


# =============================================================================
# Request/Response Models
# =============================================================================


class ResolveItemRequest(BaseModel):
    """Request to resolve a Sidekick question."""
    resolution: str


class ResolveItemResponse(BaseModel):
    """Response from resolving a Sidekick item."""
    success: bool
    item_id: str
    agent_resumed: bool = False
    message: Optional[str] = None


class UnansweredCountResponse(BaseModel):
    """Response with count of unanswered questions."""
    count: int


# =============================================================================
# Routes
# =============================================================================


@router.get("/{workspace_id}/sidekick/count")
async def get_unanswered_count(
    workspace_id: str,
    customer_id: Optional[str] = None,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> UnansweredCountResponse:
    """
    Get count of unanswered Sidekick questions.

    Used for nav badge and summary displays.
    Optionally filter by customer.
    """
    logger.info(
        "sidekick_count_requested",
        workspace_id=workspace_id,
        customer_id=customer_id,
        user_id=user.uid,
    )

    dc = get_dataconnect_client()
    sidekick = SidekickService(dc, workspace_id)
    count = await sidekick.get_unanswered_count(customer_id)

    return UnansweredCountResponse(count=count)


@router.post("/{workspace_id}/sidekick/items/{item_id}/resolve")
async def resolve_item(
    workspace_id: str,
    item_id: str,
    request: ResolveItemRequest,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> ResolveItemResponse:
    """
    Resolve a Sidekick question with an answer.

    If the question is linked to an AgentRun in waiting_for_input status,
    this will trigger the agent to resume with the provided answer.

    Args:
        workspace_id: The workspace UUID
        item_id: The Sidekick item UUID
        request: The resolution/answer

    Returns:
        Success response with agent_resumed flag
    """
    logger.info(
        "sidekick_resolve_requested",
        workspace_id=workspace_id,
        item_id=item_id,
        user_id=user.uid,
    )

    dc = get_dataconnect_client()
    sidekick = SidekickService(dc, workspace_id)

    # First, get the item to check if it's linked to an agent run
    item = await sidekick.get_item(item_id)
    if not item:
        return JSONResponse(
            status_code=404,
            content={"error": {"message": "Sidekick item not found", "code": "NOT_FOUND"}},
        )

    # SECURITY: Validate the item belongs to the requested workspace
    # This prevents cross-workspace access via item ID guessing
    item_workspace_id = item.get("workspace", {}).get("id", "")
    if item_workspace_id != workspace_id:
        logger.warning(
            "sidekick_workspace_mismatch",
            item_id=item_id,
            item_workspace=item_workspace_id,
            requested_workspace=workspace_id,
            user_id=user.uid,
        )
        return JSONResponse(
            status_code=404,
            content={"error": {"message": "Sidekick item not found", "code": "NOT_FOUND"}},
        )

    # Resolve the item
    await sidekick.resolve_item(
        item_id=item_id,
        resolution=request.resolution,
        resolved_by_user_id=user.uid,
    )

    # Check if we need to resume an agent
    agent_resumed = False
    agent_run_id = item.get("agentRun", {}).get("id") if item.get("agentRun") else None

    if agent_run_id:
        try:
            agent_service = AgentRunService(dc, workspace_id)
            run = await agent_service.get_run(agent_run_id)

            if run and run.get("status") == "waiting_for_input":
                # Resume the agent with this answer
                # Use item_id as the key for consistency - agents should create
                # sidekick items and use the returned ID as their question key
                await agent_service.resume_from_input(
                    run_id=agent_run_id,
                    answers={item_id: request.resolution},
                )
                agent_resumed = True
                logger.info(
                    "agent_resumed_from_sidekick",
                    agent_run_id=agent_run_id,
                    item_id=item_id,
                )
        except Exception as e:
            logger.warning(
                "agent_resume_failed",
                agent_run_id=agent_run_id,
                error=str(e),
            )
            # Don't fail the resolution if agent resume fails
            # The item is still resolved, agent can be resumed manually

    return ResolveItemResponse(
        success=True,
        item_id=item_id,
        agent_resumed=agent_resumed,
        message="Question resolved" + (" and agent resumed" if agent_resumed else ""),
    )


class ResyncCountsResponse(BaseModel):
    """Response from resyncing notification counts."""
    today_count: int
    sidekick_questions: int


@router.post("/{workspace_id}/notifications/resync")
async def resync_notification_counts(
    workspace_id: str,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> ResyncCountsResponse:
    """
    Resync Firestore notification counts with the database.

    Use this when counts get out of sync, e.g., after a database wipe
    or when real-time updates weren't pushed correctly.

    This queries the actual database for accurate counts and pushes
    them to Firestore, which triggers frontend real-time updates.
    """
    logger.info(
        "notification_resync_requested",
        workspace_id=workspace_id,
        user_id=user.uid,
    )

    from services.firestore_service import get_firestore_service

    firestore = get_firestore_service()
    counts = await firestore.refresh_all_counts(workspace_id)

    logger.info(
        "notification_resync_completed",
        workspace_id=workspace_id,
        counts=counts,
    )

    return ResyncCountsResponse(
        today_count=counts["today_count"],
        sidekick_questions=counts["sidekick_questions"],
    )

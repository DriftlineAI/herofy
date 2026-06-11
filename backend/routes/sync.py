"""
Sync Routes
Endpoints for integration polling and manual sync triggers.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel

from core.logging import get_logger
from middleware.auth import FirebaseUser, require_workspace_access
from middleware.scheduler_auth import verify_scheduler_token
from services.sync_orchestrator import get_sync_orchestrator

logger = get_logger("sync_routes")

router = APIRouter(tags=["sync"])


# =============================================================================
# Response Models
# =============================================================================


class PollResponse(BaseModel):
    """Response from poll endpoint."""

    success: bool
    integration_type: str
    workspaces_polled: int
    new_items: int
    errors: list[dict] = []


class ManualSyncResponse(BaseModel):
    """Response from manual sync endpoint."""

    success: bool
    message: str
    new_deals: int = 0
    triggered_agents: int = 0


# =============================================================================
# Cloud Scheduler Endpoint (OIDC Auth)
# =============================================================================


@router.post("/poll", response_model=PollResponse)
async def poll_integration(
    integration: Annotated[str, Query(description="Integration type to poll (notion, gmail, slack)")],
    workspace_id: Annotated[str | None, Query(description="Optional specific workspace to poll")] = None,
    _verified: bool = Depends(verify_scheduler_token),
) -> PollResponse:
    """
    Poll an integration for new data.

    This endpoint is called by Cloud Scheduler on a cron schedule.
    Authentication is via OIDC token from Cloud Scheduler service account.

    In development mode, authentication is bypassed.

    Query params:
        - integration: The integration type to poll (notion, gmail, slack)
        - workspace_id: Optional workspace ID to poll (if not provided, polls all)

    Returns:
        Summary of poll results
    """
    valid_integrations = ["notion", "gmail", "slack", "calendar"]
    if integration not in valid_integrations:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid integration type. Must be one of: {valid_integrations}",
        )

    logger.info(
        "poll_triggered",
        integration=integration,
        workspace_id=workspace_id,
        source="scheduler",
    )

    try:
        orchestrator = get_sync_orchestrator()
        result = await orchestrator.run_poll_for_integration(
            integration_type=integration,
            workspace_id=workspace_id,
        )

        return PollResponse(
            success=True,
            integration_type=result["integration_type"],
            workspaces_polled=result["workspaces_polled"],
            new_items=result["new_items"],
            errors=result["errors"],
        )

    except Exception as e:
        logger.exception("poll_failed", integration=integration, error=str(e))
        raise HTTPException(status_code=500, detail=f"Poll failed: {e}")


# =============================================================================
# Reset Watermark Endpoint (for re-polling)
# =============================================================================


@router.delete("/{integration_type}/watermark")
async def reset_watermark(
    integration_type: str,
    workspace_id: Annotated[str, Query(description="Workspace ID")],
    _verified: bool = Depends(verify_scheduler_token),
) -> dict:
    """
    Reset the poll watermark for an integration.

    This will cause the next poll to find all records again (deduplication
    against existing customers still applies).
    """
    from db.dataconnect_client import get_dataconnect_client

    valid_integrations = ["notion", "gmail", "slack", "calendar"]
    if integration_type not in valid_integrations:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid integration type. Must be one of: {valid_integrations}",
        )

    watermark_key = f"{integration_type}_closed_deals_watermark"

    try:
        dc = get_dataconnect_client()
        await dc.execute_mutation(
            "DeleteAgentState",
            {
                "workspaceId": workspace_id,
                "stateKey": watermark_key,
            },
        )

        logger.info(
            "watermark_reset",
            integration=integration_type,
            workspace_id=workspace_id,
        )

        return {"success": True, "message": f"Watermark reset for {integration_type}"}

    except Exception as e:
        logger.error("watermark_reset_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to reset watermark: {e}")


# =============================================================================
# Manual Sync Endpoint (Firebase Auth)
# =============================================================================


@router.post("/{integration_type}/sync", response_model=ManualSyncResponse)
async def manual_sync(
    integration_type: str,
    workspace_id: Annotated[str, Query(description="Workspace ID")],
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> ManualSyncResponse:
    """
    Manually trigger a sync for an integration.

    This endpoint is for users to manually trigger a "sync now" action
    from the UI. It's authenticated with Firebase auth.

    Path params:
        - integration_type: The integration to sync (notion, gmail, slack)

    Query params:
        - workspace_id: Workspace ID to sync

    Returns:
        Sync results
    """
    valid_integrations = ["notion", "gmail", "slack", "calendar"]
    if integration_type not in valid_integrations:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid integration type. Must be one of: {valid_integrations}",
        )

    logger.info(
        "manual_sync_triggered",
        integration=integration_type,
        workspace_id=workspace_id,
        user_id=user.uid,
    )

    try:
        # Use unified sync orchestrator for all integration types
        return await _sync_integration(workspace_id, integration_type)

    except Exception as e:
        logger.exception(
            "manual_sync_failed",
            integration=integration_type,
            workspace_id=workspace_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")


async def _sync_integration(
    workspace_id: str,
    integration_type: str,
) -> ManualSyncResponse:
    """
    Generic sync for any integration type.

    Uses SyncOrchestrator which routes through SignalWatcherEventProcessor.
    For new Notion records, this flow:
    1. NotionEventEmitter polls for changes
    2. SignalWatcherEventProcessor._handle_new_customer() creates customer via CustomerFactory
    3. Enrichment runs
    4. HandoffAuto agent is invoked with customer_id

    Args:
        workspace_id: Workspace ID
        integration_type: Integration type

    Returns:
        Sync results
    """
    try:
        orchestrator = get_sync_orchestrator()
        result = await orchestrator.run_poll_for_integration(
            integration_type=integration_type,
            workspace_id=workspace_id,
        )

        new_items = result.get("new_items", 0)
        triggered_agents = result.get("triggered_agents", 0)

        return ManualSyncResponse(
            success=True,
            message=f"Found {new_items} new items",
            new_deals=new_items,
            triggered_agents=triggered_agents,
        )

    except Exception as e:
        logger.error(
            "sync_failed",
            workspace_id=workspace_id,
            integration_type=integration_type,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail=f"{integration_type.capitalize()} sync failed: {e}",
        )

"""
Customer Enrichment API Routes

Endpoints for triggering and monitoring AI-powered customer enrichment.
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from core.logging import get_logger
from middleware.auth import FirebaseUser, require_workspace_access
from services.enrichment_service import EnrichmentService, process_enrichment_queue

logger = get_logger("EnrichmentRoutes")

router = APIRouter(prefix="/enrichment", tags=["enrichment"])


# =============================================================================
# Response Models
# =============================================================================


class EnrichmentTriggerResponse(BaseModel):
    """Response after triggering enrichment."""
    status: str
    message: str


class EnrichmentStatusResponse(BaseModel):
    """Current enrichment queue status."""
    pending_count: int
    oldest_pending_created_at: str | None = None


class EnrichmentResultResponse(BaseModel):
    """Result of a single customer enrichment."""
    status: str
    customer_id: str
    stakeholders_created: int = 0
    goals_created: int = 0
    signals_created: int = 0
    error: str | None = None


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/trigger")
async def trigger_enrichment_batch(
    workspace_id: Annotated[str, Query(description="Workspace ID")],
    background_tasks: BackgroundTasks,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> EnrichmentTriggerResponse:
    """
    Trigger background enrichment processing for pending customers.

    This starts a background task that processes customers with
    enrichmentStatus='pending'. The task continues until all
    pending customers are processed or an error occurs.

    Typically called automatically after a bulk import, but can
    be triggered manually to retry failed enrichments or process
    customers added without triggering enrichment.
    """
    logger.info(
        "enrichment_trigger_requested",
        workspace_id=workspace_id,
        user_id=user.uid,
    )

    # Add background task
    background_tasks.add_task(process_enrichment_queue, workspace_id)

    return EnrichmentTriggerResponse(
        status="started",
        message="Enrichment processing started in background",
    )


@router.get("/status")
async def get_enrichment_status(
    workspace_id: Annotated[str, Query(description="Workspace ID")],
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> EnrichmentStatusResponse:
    """
    Get the current enrichment queue status.

    Returns the count of customers pending enrichment and
    the creation time of the oldest pending customer.
    """
    service = EnrichmentService(workspace_id)
    pending = await service.get_pending_customers(limit=1000)

    oldest_created_at = None
    if pending:
        oldest_created_at = pending[0].get("createdAt")

    return EnrichmentStatusResponse(
        pending_count=len(pending),
        oldest_pending_created_at=oldest_created_at,
    )


@router.post("/customers/{customer_id}")
async def enrich_single_customer(
    customer_id: str,
    workspace_id: Annotated[str, Query(description="Workspace ID")],
    background_tasks: BackgroundTasks,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> EnrichmentTriggerResponse:
    """
    Trigger enrichment for a single customer.

    Use this to re-enrich a customer after updating their raw notes,
    or to retry a failed enrichment.
    """
    from db.dataconnect_client import get_dataconnect_client

    logger.info(
        "single_enrichment_requested",
        workspace_id=workspace_id,
        customer_id=customer_id,
        user_id=user.uid,
    )

    # Fetch customer data
    dc = get_dataconnect_client()
    result = await dc.execute_query("GetCustomer", {"id": customer_id})
    customer = result.get("customer")

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Mark as pending (will be picked up by background processor)
    await dc.execute_mutation(
        "UpdateCustomerEnrichmentStatus",
        {
            "id": customer_id,
            "enrichmentStatus": "pending",
            "enrichmentAttempts": 0,
            "enrichmentError": None,
        },
    )

    # Trigger background processing
    background_tasks.add_task(process_enrichment_queue, workspace_id)

    return EnrichmentTriggerResponse(
        status="queued",
        message=f"Enrichment queued for {customer.get('name', customer_id)}",
    )


@router.post("/customers/{customer_id}/sync")
async def enrich_customer_sync(
    customer_id: str,
    workspace_id: Annotated[str, Query(description="Workspace ID")],
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> EnrichmentResultResponse:
    """
    Synchronously enrich a single customer (for testing/debugging).

    Unlike the async endpoint, this waits for enrichment to complete
    and returns the results immediately. Use for testing or when
    you need immediate feedback.
    """
    from db.dataconnect_client import get_dataconnect_client

    logger.info(
        "sync_enrichment_requested",
        workspace_id=workspace_id,
        customer_id=customer_id,
        user_id=user.uid,
    )

    # Fetch customer data
    dc = get_dataconnect_client()
    result = await dc.execute_query("GetCustomer", {"id": customer_id})
    customer = result.get("customer")

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    try:
        service = EnrichmentService(workspace_id)
        result = await service.process_and_save_enrichment(
            customer_id=customer_id,
            customer_name=customer.get("name", "Unknown"),
            raw_notes=customer.get("rawNotes"),
            existing_tier=customer.get("tier"),
            existing_arr_cents=customer.get("arrCents"),
            existing_lifecycle=customer.get("lifecycle"),
        )

        return EnrichmentResultResponse(
            status="completed",
            customer_id=customer_id,
            stakeholders_created=result.get("stakeholders_created", 0),
            goals_created=result.get("goals_created", 0),
            signals_created=result.get("signals_created", 0),
        )

    except Exception as e:
        logger.error(
            "sync_enrichment_failed",
            customer_id=customer_id,
            error=str(e),
        )
        return EnrichmentResultResponse(
            status="failed",
            customer_id=customer_id,
            error=str(e),
        )

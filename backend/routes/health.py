"""
Health Check Routes
Server health and readiness endpoints
"""

from fastapi import APIRouter, Depends

from core.types import HealthResponse
from db.dataconnect_client import get_dataconnect_client

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Basic health check endpoint.
    Returns 200 if the server is running.
    """
    return HealthResponse(status="ok", version="1.0.0")


@router.get("/ready")
async def readiness_check() -> dict:
    """
    Readiness check that verifies database connectivity.
    Used by Kubernetes/Cloud Run for readiness probes.
    """
    try:
        dc = get_dataconnect_client()
        # Simple query to verify DataConnect connection
        # We'll use a lightweight query - checking if we can list workspaces
        result = await dc.execute_query("GetWorkspaces", {})
        if result is not None:
            return {"status": "ready", "database": "connected"}
    except Exception as e:
        return {"status": "not_ready", "database": str(e)}

    return {"status": "not_ready", "database": "unknown"}

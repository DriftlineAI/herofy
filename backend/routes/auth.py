"""
Auth routes — custom-claims sync.

`POST /api/auth/sync-claims` recomputes the caller's workspace memberships and writes them to
their `ws` custom claim (used by Firestore security rules for tenant isolation). A user can only
sync their OWN claims — the uid comes from the verified token, never from the request body.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from core.logging import get_logger
from middleware.auth import FirebaseUser, get_current_user
from services.claims_service import sync_workspace_claims

logger = get_logger("auth_routes")

router = APIRouter(tags=["Auth"])


@router.post("/auth/sync-claims")
async def sync_claims(user: FirebaseUser = Depends(get_current_user)) -> dict:
    """Sync the caller's workspace-membership custom claims. Returns the workspace ids written.

    The client must call `getIdToken(true)` afterward to refresh the token with the new claim.
    """
    try:
        workspaces = await sync_workspace_claims(user.uid)
        return {"workspaces": workspaces}
    except Exception as e:  # noqa: BLE001 - surface a clean error (with CORS headers) not an unhandled 500
        logger.error("sync_claims_failed", uid=user.uid, error=str(e))
        return JSONResponse(
            status_code=503,
            content={"error": {"code": "CLAIMS_SYNC_FAILED", "message": str(e)}},
        )

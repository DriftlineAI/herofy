"""
Workspace membership -> Firebase custom claims sync.

Firestore security rules cannot query CloudSQL (where `WorkspaceMember` lives), so we publish
the set of workspace ids a user belongs to as a `ws` custom claim on their Firebase Auth token.
Rules then enforce per-workspace (tenant) isolation with `request.auth.token.ws.hasAny([wsId])`.

The claim stores DASHED workspace ids to match the Firestore document-id format
(`_normalize_uuid`, mirrored by the frontend's `normalizeUuid`).

Token freshness: after this runs, the client must call `getIdToken(true)` to pick up the new
claim. Callers (provisioning, join-approval, login bootstrap) do that refresh.
"""
import asyncio

from firebase_admin import auth

from core.logging import get_logger
from db.dataconnect_client import get_dataconnect_client
from services.firestore_service import _normalize_uuid

logger = get_logger("claims")


async def sync_workspace_claims(uid: str) -> list[str]:
    """Recompute `uid`'s workspace memberships and write them to the `ws` custom claim.

    Returns the dashed workspace ids written (also useful for the caller to verify).
    """
    dc = get_dataconnect_client()
    data = await dc.execute_query("GetUserById", {"userId": uid})
    users = data.get("users") or []
    memberships = (users[0].get("workspaceMembers_on_user") if users else None) or []
    ws_ids = sorted({
        _normalize_uuid(m["workspace"]["id"])
        for m in memberships
        if m.get("workspace") and m["workspace"].get("id")
    })

    def _write() -> None:
        # Merge so we never clobber unrelated custom claims that may be added later.
        existing = {}
        try:
            existing = dict(auth.get_user(uid).custom_claims or {})
        except Exception:  # noqa: BLE001 - first-time user / lookup miss: start fresh
            existing = {}
        existing["ws"] = ws_ids
        auth.set_custom_user_claims(uid, existing)

    await asyncio.to_thread(_write)
    logger.info("workspace_claims_synced", uid=uid, workspaces=len(ws_ids))
    return ws_ids

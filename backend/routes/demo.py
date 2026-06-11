"""
Demo provisioning — per-visitor anonymous sandbox (demo.herofy.ai).

`POST /demo/provision` takes an anonymous Firebase user, creates an isolated `demo-*` workspace
with that user as owner (on the admin DataConnect surface, which bypasses @auth), seeds the
Northcrest demo fixture, and mints the user's `ws` custom claim so Firestore tenant rules admit
them. Idempotent: a uid that already owns a workspace gets it back instead of a second one.

Mounted only when settings.demo_enabled (see main.py). Anonymous tokens are admitted to this
endpoint by the demo allowlist in middleware/auth.py; every data op still enforces workspace
membership via @check and the workspace id is unguessable, so visitors are isolated to their own
sandbox.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException

from core.logging import get_logger
from config import settings
from middleware.auth import FirebaseUser, get_current_user
from db.dataconnect_client import get_dataconnect_client
from services.claims_service import sync_workspace_claims
from orchestrator.demo import seed_workspace

logger = get_logger("demo_routes")

router = APIRouter(prefix="/demo", tags=["Demo"])


@router.post("/provision")
async def provision_demo_workspace(user: FirebaseUser = Depends(get_current_user)) -> dict:
    """Create + seed an isolated demo workspace for the (anonymous) caller, then sync their claims."""
    if not settings.demo_enabled:
        raise HTTPException(status_code=404, detail="Demo mode is not enabled")

    dc = get_dataconnect_client()

    # Idempotency: if this uid already owns a workspace (refresh / double-tap), reuse it.
    user_rows = (await dc.execute_query("GetUserById", {"userId": user.uid})).get("users", [])
    memberships = (user_rows[0].get("workspaceMembers_on_user") or []) if user_rows else []
    if memberships:
        workspace_id = memberships[0]["workspace"]["id"]
        await sync_workspace_claims(user.uid)
        logger.info("demo_provision_reused", uid=user.uid, workspace_id=workspace_id)
        return {"workspace_id": workspace_id, "reused": True}

    workspace_id = str(uuid.uuid4())
    slug = f"demo-{user.uid[:12].lower()}"

    # Create the user row impersonated AS the anon user: User.id defaults to auth.uid, so the insert
    # needs an auth.uid context. get_current_user already set request-scoped impersonation to this
    # uid, and CreateUserWithId references auth.uid (id_expr), so the client impersonates it → id =
    # auth.uid = this uid. Then the workspace + owner membership run on the pure-admin surface.
    # setupCompleted / hasCompletedSetup = True so the demo skips the setup wizard.
    await dc.execute_mutation("CreateUserWithId", {
        "id": user.uid,  # ignored — CreateUserWithId forces id = auth.uid
        "email": f"{user.uid}@demo.herofy.ai",
        "displayName": "Demo",
    })
    await dc.execute_mutation("CreateWorkspaceWithId", {
        "id": workspace_id,
        "name": "Herofy Demo",
        "slug": slug,
        "setupCompleted": True,
    })
    # AddWorkspaceMemberPublic (NO_ACCESS, browser-uncallable, no @check) — the admin surface adds
    # the owner directly without the membership-bootstrap @check that AddWorkspaceMember carries.
    await dc.execute_mutation("AddWorkspaceMemberPublic", {
        "workspaceId": workspace_id,
        "userId": user.uid,
        "role": "owner",
        "hasCompletedSetup": True,
    })

    # Seed AS the demo user (now a member) so the seed ops' @check membership gates pass on the
    # admin surface — auth.uid is unreadable there without impersonation.
    with dc.impersonate(user.uid):
        result = await seed_workspace(workspace_id, profile="full")

    # Mint the `ws` claim so Firestore tenant rules (notifications / agent_status) admit this user.
    # The client must call getIdToken(true) afterward to pick it up.
    await sync_workspace_claims(user.uid)

    logger.info("demo_provisioned", uid=user.uid, workspace_id=workspace_id,
                counts=result.counts, errors=len(result.errors))
    return {
        "workspace_id": workspace_id,
        "reused": False,
        "counts": result.counts,
        "errors": result.errors,
    }

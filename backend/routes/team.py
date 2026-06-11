"""
Team Management Routes
Handles workspace invitations and member management.
"""

import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from firebase_admin import auth as firebase_auth
from pydantic import BaseModel, EmailStr

from services.claims_service import sync_workspace_claims

from config import settings
from core.logging import get_logger
from core.permissions import (
    Action,
    Resource,
    can_access,
    check_can_invite,
    check_can_remove_member,
    check_can_change_role,
    PermissionDenied,
)
from middleware.auth import FirebaseUser, require_workspace_access, get_current_user

logger = get_logger("team")

# Workspace-scoped routes (require workspace access)
router = APIRouter(tags=["Team Management"])


# =============================================================================
# Request/Response Models
# =============================================================================


class InviteMemberRequest(BaseModel):
    """Request to invite a member to the workspace."""
    email: EmailStr
    role: str  # "admin" or "member"


class InviteMemberResponse(BaseModel):
    """Response with invitation details."""
    invitation_id: str
    invite_link: str
    email: str
    role: str
    expires_at: str


class AcceptInvitationResponse(BaseModel):
    """Response after accepting an invitation."""
    workspace_id: str
    workspace_slug: str
    workspace_name: str
    role: str


class InvitationDetailsResponse(BaseModel):
    """Public invitation details (for accept page)."""
    workspace_name: str
    role: str
    invited_by_name: Optional[str]
    invited_by_email: str
    email: str
    expires_at: str
    is_expired: bool
    status: str


class MemberResponse(BaseModel):
    """Workspace member details."""
    user_id: str
    email: str
    display_name: Optional[str]
    avatar_url: Optional[str]
    role: str
    joined_at: str


class UpdateMemberRoleRequest(BaseModel):
    """Request to change a member's role."""
    role: str  # "admin" or "member"


class PendingInvitationResponse(BaseModel):
    """Pending invitation details for admin view."""
    id: str
    email: str
    role: str
    expires_at: str
    created_at: str
    invited_by_name: Optional[str]
    invited_by_email: str


# =============================================================================
# Helper Functions
# =============================================================================


def generate_invitation_token() -> str:
    """Generate a cryptographically secure invitation token."""
    return secrets.token_urlsafe(32)  # 256 bits of entropy


def get_invite_link(token: str) -> str:
    """Generate the full invitation link."""
    base_url = settings.get_app_base_url_with_fallback()
    return f"{base_url}/invite/{token}"


def calculate_expiry() -> datetime:
    """Calculate invitation expiry (7 days from now)."""
    return datetime.now(timezone.utc) + timedelta(days=7)


def is_expired(expires_at: datetime | str) -> bool:
    """Check if an invitation has expired."""
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    return datetime.now(timezone.utc) > expires_at


# =============================================================================
# Workspace-Scoped Endpoints (require workspace access)
# =============================================================================


@router.post("/workspaces/{workspace_id}/invitations", response_model=InviteMemberResponse)
async def invite_member(
    workspace_id: str,
    request: InviteMemberRequest,
    user: FirebaseUser = Depends(require_workspace_access()),
):
    """
    Invite a user to the workspace by email.

    Requires admin or owner role.
    """
    from db.dataconnect_client import get_dataconnect_client

    # Check permission
    try:
        check_can_invite(user.role, request.role)
    except PermissionDenied as e:
        raise HTTPException(status_code=403, detail=e.message)

    dc = get_dataconnect_client()

    # Get workspace details
    workspace_result = await dc.execute_query(
        "GetWorkspace",
        {"id": workspace_id},
    )
    workspace = workspace_result.get("workspace", {})

    # Check if email is already a member
    existing_check = await dc.execute_query(
        "CheckWorkspaceMembership",
        {"workspaceId": workspace_id, "userId": request.email},  # Approximation - need email lookup
    )

    # Check for existing pending invitation
    existing_invitation = await dc.execute_query(
        "CheckExistingInvitation",
        {"workspaceId": workspace_id, "email": request.email},
    )

    if existing_invitation.get("workspaceInvitations"):
        raise HTTPException(
            status_code=409,
            detail="An invitation for this email already exists"
        )

    # Generate token and calculate expiry
    token = generate_invitation_token()
    expires_at = calculate_expiry()

    # Create invitation
    await dc.execute_mutation(
        "CreateInvitation",
        {
            "workspaceId": workspace_id,
            "email": request.email,
            "role": request.role,
            "invitedByUserId": user.uid,
            "token": token,
            "expiresAt": expires_at.isoformat(),
        },
    )

    invite_link = get_invite_link(token)

    logger.info(
        "invitation_created",
        workspace_id=workspace_id,
        email=request.email,
        role=request.role,
        invited_by=user.uid,
    )

    # Send invitation email (best effort)
    try:
        from services.email import send_invitation_email
        await send_invitation_email(
            to_email=request.email,
            workspace_name=workspace.get("name", ""),
            inviter_name=user.name or user.email,
            invite_link=invite_link,
            role=request.role,
        )
    except Exception as e:
        logger.warning(
            "invitation_email_failed",
            email=request.email,
            error=str(e)
        )

    return InviteMemberResponse(
        invitation_id=token,  # Token serves as ID for URL
        invite_link=invite_link,
        email=request.email,
        role=request.role,
        expires_at=expires_at.isoformat(),
    )


@router.get("/workspaces/{workspace_id}/invitations")
async def list_pending_invitations(
    workspace_id: str,
    user: FirebaseUser = Depends(require_workspace_access()),
):
    """
    List all pending invitations for the workspace.

    Requires admin or owner role.
    """
    from db.dataconnect_client import get_dataconnect_client

    # Check permission (VIEW_TEAM covers viewing invitations)
    try:
        can_access(user.role, Action.VIEW_TEAM)
    except PermissionDenied as e:
        raise HTTPException(status_code=403, detail=e.message)

    dc = get_dataconnect_client()

    result = await dc.execute_query(
        "GetPendingInvitations",
        {"workspaceId": workspace_id},
    )

    invitations = result.get("workspaceInvitations", [])

    return [
        PendingInvitationResponse(
            id=inv["id"],
            email=inv["email"],
            role=inv["role"],
            expires_at=inv["expiresAt"],
            created_at=inv["createdAt"],
            invited_by_name=inv.get("invitedByUser", {}).get("displayName"),
            invited_by_email=inv.get("invitedByUser", {}).get("email", ""),
        )
        for inv in invitations
    ]


@router.delete("/workspaces/{workspace_id}/invitations/{invitation_id}")
async def revoke_invitation(
    workspace_id: str,
    invitation_id: str,
    user: FirebaseUser = Depends(require_workspace_access()),
):
    """
    Revoke a pending invitation.

    Requires admin or owner role.
    """
    from db.dataconnect_client import get_dataconnect_client

    # Check permission
    try:
        can_access(user.role, Action.INVITE_MEMBER)  # Same permission as invite
    except PermissionDenied as e:
        raise HTTPException(status_code=403, detail=e.message)

    dc = get_dataconnect_client()

    await dc.execute_mutation(
        "RevokeInvitation",
        {"id": invitation_id},
    )

    logger.info(
        "invitation_revoked",
        workspace_id=workspace_id,
        invitation_id=invitation_id,
        revoked_by=user.uid,
    )

    return {"status": "revoked"}


@router.get("/workspaces/{workspace_id}/members")
async def list_members(
    workspace_id: str,
    user: FirebaseUser = Depends(require_workspace_access()),
):
    """
    List all members of the workspace.

    Any workspace member can view the member list.
    """
    from db.dataconnect_client import get_dataconnect_client

    dc = get_dataconnect_client()

    result = await dc.execute_query(
        "GetWorkspaceMembers",
        {"workspaceId": workspace_id},
    )

    members = result.get("workspaceMembers", [])

    return [
        MemberResponse(
            user_id=member.get("user", {}).get("id", ""),
            email=member.get("user", {}).get("email", ""),
            display_name=member.get("user", {}).get("displayName"),
            avatar_url=member.get("user", {}).get("avatarUrl"),
            role=member["role"],
            joined_at=member["joinedAt"],
        )
        for member in members
    ]


@router.patch("/workspaces/{workspace_id}/members/{member_id}")
async def update_member_role(
    workspace_id: str,
    member_id: str,
    request: UpdateMemberRoleRequest,
    user: FirebaseUser = Depends(require_workspace_access()),
):
    """
    Change a member's role.

    - Owner can change any role (except their own)
    - Admin can change member <-> admin (not owner)
    - Member cannot change roles
    """
    from db.dataconnect_client import get_dataconnect_client

    dc = get_dataconnect_client()

    # Get target member's current role
    target_membership = await dc.execute_query(
        "CheckWorkspaceMembership",
        {"workspaceId": workspace_id, "userId": member_id},
    )

    members = target_membership.get("workspaceMembers", [])
    if not members:
        raise HTTPException(status_code=404, detail="Member not found")

    current_role = members[0]["role"]

    # Cannot change your own role
    if member_id == user.uid:
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    # Check permission
    try:
        check_can_change_role(user.role, current_role, request.role)
    except PermissionDenied as e:
        raise HTTPException(status_code=403, detail=e.message)

    # Update role
    await dc.execute_mutation(
        "UpdateMemberRole",
        {
            "workspaceId": workspace_id,
            "userId": member_id,
            "role": request.role,
        },
    )

    logger.info(
        "member_role_changed",
        workspace_id=workspace_id,
        member_id=member_id,
        old_role=current_role,
        new_role=request.role,
        changed_by=user.uid,
    )

    return {"status": "updated", "role": request.role}


@router.delete("/workspaces/{workspace_id}/members/{member_id}")
async def remove_member(
    workspace_id: str,
    member_id: str,
    user: FirebaseUser = Depends(require_workspace_access()),
):
    """
    Remove a member from the workspace.

    - Owner can remove anyone except themselves
    - Admin can remove members, but not owner or other admins
    - Member cannot remove anyone
    """
    from db.dataconnect_client import get_dataconnect_client

    dc = get_dataconnect_client()

    # Cannot remove yourself
    if member_id == user.uid:
        raise HTTPException(status_code=400, detail="Cannot remove yourself from workspace")

    # Get target member's role
    target_membership = await dc.execute_query(
        "CheckWorkspaceMembership",
        {"workspaceId": workspace_id, "userId": member_id},
    )

    members = target_membership.get("workspaceMembers", [])
    if not members:
        raise HTTPException(status_code=404, detail="Member not found")

    target_role = members[0]["role"]

    # Check permission
    try:
        check_can_remove_member(user.role, target_role)
    except PermissionDenied as e:
        raise HTTPException(status_code=403, detail=e.message)

    # Remove member
    await dc.execute_mutation(
        "RemoveWorkspaceMember",
        {
            "workspaceId": workspace_id,
            "userId": member_id,
        },
    )

    # Tenant isolation: recompute the removed user's `ws` custom claim (now without this workspace)
    # and revoke their refresh tokens, so the stale claim can't outlive their current ID token
    # (Firestore reads of this workspace stop within <=1h, when their token can no longer refresh).
    try:
        await sync_workspace_claims(member_id)
        await asyncio.to_thread(firebase_auth.revoke_refresh_tokens, member_id)
    except Exception as e:  # noqa: BLE001 - removal already succeeded; claim cleanup is best-effort
        logger.warning("member_removal_claim_revoke_failed", member_id=member_id, error=str(e))

    logger.info(
        "member_removed",
        workspace_id=workspace_id,
        member_id=member_id,
        removed_by=user.uid,
    )

    return {"status": "removed"}


# =============================================================================
# Public Endpoints (for invitation acceptance)
# =============================================================================


# Public router for invitation acceptance (no workspace auth required)
public_router = APIRouter(tags=["Invitations"])


@public_router.get("/invitations/{token}", response_model=InvitationDetailsResponse)
async def get_invitation_details(token: str):
    """
    Get invitation details by token (public endpoint).

    This is used to display the invitation acceptance page.
    """
    from db.dataconnect_client import get_dataconnect_client

    dc = get_dataconnect_client()

    result = await dc.execute_query(
        "GetInvitationByToken",
        {"token": token},
    )

    invitations = result.get("workspaceInvitations", [])
    if not invitations:
        raise HTTPException(status_code=404, detail="Invitation not found")

    invitation = invitations[0]

    # Check status
    if invitation["status"] != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Invitation is no longer valid (status: {invitation['status']})"
        )

    expires_at = invitation["expiresAt"]
    expired = is_expired(expires_at)

    return InvitationDetailsResponse(
        workspace_name=invitation.get("workspace", {}).get("name", ""),
        role=invitation["role"],
        invited_by_name=invitation.get("invitedByUser", {}).get("displayName"),
        invited_by_email=invitation.get("invitedByUser", {}).get("email", ""),
        email=invitation["email"],
        expires_at=expires_at,
        is_expired=expired,
        status=invitation["status"],
    )


@public_router.post("/invitations/{token}/accept", response_model=AcceptInvitationResponse)
async def accept_invitation(
    token: str,
    user: FirebaseUser = Depends(get_current_user),
):
    """
    Accept an invitation and join the workspace.

    Requires authentication (user must be logged in).
    """
    from db.dataconnect_client import get_dataconnect_client

    dc = get_dataconnect_client()

    # Get invitation
    result = await dc.execute_query(
        "GetInvitationByToken",
        {"token": token},
    )

    invitations = result.get("workspaceInvitations", [])
    if not invitations:
        raise HTTPException(status_code=404, detail="Invitation not found")

    invitation = invitations[0]

    # Check status
    if invitation["status"] != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Invitation is no longer valid (status: {invitation['status']})"
        )

    # Check expiry
    if is_expired(invitation["expiresAt"]):
        raise HTTPException(
            status_code=400,
            detail="This invitation has expired. Ask your admin to send a new one."
        )

    workspace_id = invitation.get("workspace", {}).get("id")
    workspace_name = invitation.get("workspace", {}).get("name", "")
    workspace_slug = invitation.get("workspace", {}).get("slug", "")

    # Check if user is already a member
    existing = await dc.execute_query(
        "CheckExistingMembership",
        {"workspaceId": workspace_id, "userId": user.uid},
    )

    if existing.get("workspaceMembers"):
        raise HTTPException(
            status_code=409,
            detail="You are already a member of this workspace"
        )

    # Add user to workspace
    await dc.execute_mutation(
        "AddWorkspaceMember",
        {
            "workspaceId": workspace_id,
            "userId": user.uid,
            "role": invitation["role"],
        },
    )

    # Update invitation status
    await dc.execute_mutation(
        "AcceptInvitation",
        {
            "id": invitation["id"],
            "acceptedByUserId": user.uid,
        },
    )

    logger.info(
        "invitation_accepted",
        workspace_id=workspace_id,
        user_id=user.uid,
        user_email=user.email,
        invited_email=invitation["email"],
        role=invitation["role"],
    )

    return AcceptInvitationResponse(
        workspace_id=workspace_id,
        workspace_slug=workspace_slug,
        workspace_name=workspace_name,
        role=invitation["role"],
    )


# =============================================================================
# Workspace Join Requests
# =============================================================================


class JoinRequestRequest(BaseModel):
    """Request to join a workspace."""
    workspace_id: str


class JoinRequestResponse(BaseModel):
    """Response after requesting to join."""
    success: bool
    message: str


@public_router.post("/workspaces/join-requests", response_model=JoinRequestResponse)
async def request_to_join_workspace(
    request: JoinRequestRequest,
    user: FirebaseUser = Depends(get_current_user),
):
    """
    Request to join an existing workspace.

    Sends email to all workspace owners for approval.
    Requires authentication (user must be logged in).
    """
    from db.dataconnect_client import get_dataconnect_client
    from services.email import send_join_request_notification

    dc = get_dataconnect_client()

    # Get workspace details
    workspace_result = await dc.execute_query(
        "GetWorkspace",
        {"id": request.workspace_id},
    )

    workspace = workspace_result.get("workspace")
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace_name = workspace.get("name", "")

    # Check if user is already a member
    existing = await dc.execute_query(
        "CheckWorkspaceMembership",
        {"workspaceId": request.workspace_id, "userId": user.uid},
    )

    if existing.get("workspaceMembers"):
        raise HTTPException(
            status_code=409,
            detail="You are already a member of this workspace"
        )

    # Create join request
    await dc.execute_mutation(
        "CreateWorkspaceJoinRequest",
        {
            "workspaceId": request.workspace_id,
            "userId": user.uid,
            "userEmail": user.email,
        },
    )

    logger.info(
        "join_request_created",
        workspace_id=request.workspace_id,
        user_id=user.uid,
        user_email=user.email,
    )

    # Get workspace owners to notify
    members_result = await dc.execute_query(
        "GetWorkspaceMembers",
        {"workspaceId": request.workspace_id},
    )

    members = members_result.get("workspaceMembers", [])
    owners = [
        m for m in members
        if m.get("role") == "owner"
    ]

    # Send email to each owner (best effort)
    for owner in owners:
        owner_email = owner.get("user", {}).get("email")
        if owner_email:
            try:
                await send_join_request_notification(
                    workspace_name=workspace_name,
                    workspace_id=request.workspace_id,
                    requester_email=user.email,
                    requester_name=user.name,
                    owner_email=owner_email,
                )
            except Exception as e:
                logger.warning(
                    "join_request_notification_failed",
                    owner_email=owner_email,
                    error=str(e)
                )

    return JoinRequestResponse(
        success=True,
        message="Request sent! You'll be notified when an owner approves.",
    )


# =============================================================================
# Workspace Lookup (Public)
# =============================================================================


class WorkspaceByDomainResponse(BaseModel):
    """Workspace found by domain."""
    id: str
    name: str
    member_count: int
    is_current_user_member: bool
    setup_completed: bool


@public_router.get("/workspaces/by-domain/{domain}")
async def get_workspace_by_domain(
    domain: str,
    user: Optional[FirebaseUser] = Depends(get_current_user),
):
    """
    Find workspace by email domain (public endpoint for signup flow).

    Returns workspace info if found, 404 if not.
    Includes is_current_user_member flag if user is authenticated.
    """
    from db.dataconnect_client import get_dataconnect_client

    dc = get_dataconnect_client()

    result = await dc.execute_query(
        "GetWorkspaceByDomain",
        {"domain": domain},
    )

    workspaces = result.get("workspaces", [])
    if not workspaces:
        raise HTTPException(status_code=404, detail="No workspace found for this domain")

    workspace = workspaces[0]
    workspace_id = workspace["id"]
    workspace_name = workspace["name"]
    setup_completed = workspace.get("setupCompleted", False)
    members = workspace.get("workspaceMembers_on_workspace", [])
    member_count = len(members)

    # Check if current user is already a member
    is_member = False
    member_details = []
    current_user_has_completed_setup = False

    if user:
        for m in members:
            user_data = m.get("user", {})
            member_details.append({
                "user_id": user_data.get("id"),
                "email": user_data.get("email"),
                "role": m.get("role"),
                "has_completed_setup": m.get("hasCompletedSetup"),
            })

        member_user_ids = [m.get("user", {}).get("id") for m in members]
        is_member = user.uid in member_user_ids

        # Find current user's membership details
        current_user_membership = next(
            (md for md in member_details if md.get("user_id") == user.uid),
            None
        )
        if current_user_membership:
            current_user_has_completed_setup = current_user_membership.get("has_completed_setup", False)

        # Find owner email
        owner_members = [md for md in member_details if md.get("role") == "owner"]
        owner_email = owner_members[0].get("email") if owner_members else None

        logger.info(
            "workspace_lookup_debug",
            domain=domain,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            workspace_setup_completed=setup_completed,
            current_user_uid=user.uid,
            current_user_email=user.email,
            current_user_has_completed_setup=current_user_has_completed_setup,
            owner_email=owner_email,
            member_details=member_details,
            member_user_ids=member_user_ids,
            is_member=is_member,
            member_count=member_count,
        )
    else:
        logger.info(
            "workspace_lookup_no_auth",
            domain=domain,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
        )

    return WorkspaceByDomainResponse(
        id=workspace_id,
        name=workspace_name,
        member_count=member_count,
        is_current_user_member=is_member,
        setup_completed=setup_completed,
    )


# =============================================================================
# Complete Setup (for existing members)
# =============================================================================


class CompleteSetupRequest(BaseModel):
    workspace_id: str
    user_id: str


@public_router.post("/complete-setup")
async def complete_setup(
    request: CompleteSetupRequest,
    user: FirebaseUser = Depends(get_current_user),
):
    """
    Mark workspace setup as complete for a user.
    
    Used when user is already a member but hasCompletedSetup is false/null.
    """
    from db.dataconnect_client import get_dataconnect_client

    # Verify the user_id matches the authenticated user
    if request.user_id != user.uid:
        raise HTTPException(status_code=403, detail="Cannot complete setup for another user")

    dc = get_dataconnect_client()

    try:
        await dc.execute_mutation(
            "CompleteWorkspaceSetup",
            {
                "workspaceId": request.workspace_id,
                "userId": request.user_id,
            },
        )

        logger.info(
            "setup_completed",
            workspace_id=request.workspace_id,
            user_id=request.user_id,
            user_email=user.email,
        )

        return {"success": True}

    except Exception as e:
        logger.error(
            "setup_completion_failed",
            workspace_id=request.workspace_id,
            user_id=request.user_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Failed to complete setup")


# =============================================================================
# Mark Workspace Setup Complete
# =============================================================================


class MarkWorkspaceSetupCompleteRequest(BaseModel):
    workspace_id: str


@public_router.post("/mark-workspace-setup-complete")
async def mark_workspace_setup_complete(
    request: MarkWorkspaceSetupCompleteRequest,
    user: FirebaseUser = Depends(get_current_user),
):
    """
    Mark workspace setup as complete.
    
    Called when the workspace owner finishes the setup wizard.
    This prevents future users from going through workspace setup again.
    """
    from db.dataconnect_client import get_dataconnect_client

    dc = get_dataconnect_client()

    # Verify user is a member of the workspace (ideally should be owner, but we'll allow any member for now)
    membership_check = await dc.execute_query(
        "CheckWorkspaceMembership",
        {"workspaceId": request.workspace_id, "userId": user.uid},
    )

    if not membership_check.get("workspaceMembers"):
        raise HTTPException(
            status_code=403,
            detail="You must be a member of this workspace to mark setup complete"
        )

    try:
        await dc.execute_mutation(
            "MarkWorkspaceSetupComplete",
            {"workspaceId": request.workspace_id},
        )

        logger.info(
            "workspace_setup_completed",
            workspace_id=request.workspace_id,
            completed_by_user_id=user.uid,
            completed_by_email=user.email,
        )

        return {"success": True}

    except Exception as e:
        logger.error(
            "workspace_setup_completion_failed",
            workspace_id=request.workspace_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Failed to mark workspace setup complete")

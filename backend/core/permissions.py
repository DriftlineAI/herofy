"""
Herofy Permission Primitive
Single entry point for all permission checks (RBAC).

Philosophy:
- Roles gate administrative power, not customer data access
- Workspace membership = full access to all customer data
- Roles: owner > admin > member
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from core.errors import HerofyError


class PermissionDenied(HerofyError):
    """User lacks permission for requested action."""

    def __init__(self, action: str, reason: str):
        super().__init__(
            message=f"Permission denied for {action}: {reason}",
            code="PERMISSION_DENIED",
            details={"action": action, "reason": reason},
        )


class Action(Enum):
    """Actions that can be permission-checked."""

    # =========================================================================
    # Customer-data actions (any workspace member can do)
    # =========================================================================
    VIEW_CUSTOMER = "view_customer"
    EDIT_CUSTOMER = "edit_customer"
    VIEW_THREAD = "view_thread"
    SEND_MESSAGE = "send_message"
    VIEW_MEETING = "view_meeting"
    EDIT_MEETING = "edit_meeting"
    APPROVE_PLAN = "approve_plan"
    VIEW_HANDBOOK = "view_handbook"
    EDIT_HANDBOOK = "edit_handbook"
    VIEW_NEED = "view_need"
    RESOLVE_NEED = "resolve_need"
    VIEW_AGENT_RUN = "view_agent_run"
    ANSWER_AGENT_QUESTION = "answer_agent_question"

    # =========================================================================
    # Admin actions (admin or owner)
    # =========================================================================
    INVITE_MEMBER = "invite_member"
    REMOVE_MEMBER = "remove_member"
    CHANGE_ROLE = "change_role"
    EDIT_WORKSPACE_SETTINGS = "edit_workspace_settings"
    MANAGE_INTEGRATIONS = "manage_integrations"
    VIEW_BILLING = "view_billing"
    VIEW_TEAM = "view_team"  # View member list

    # =========================================================================
    # Owner-only actions
    # =========================================================================
    MANAGE_BILLING = "manage_billing"
    DELETE_WORKSPACE = "delete_workspace"
    TRANSFER_OWNERSHIP = "transfer_ownership"


@dataclass
class Resource:
    """
    Resource being accessed.

    For now, resource details are not consulted for customer-data actions
    (membership is sufficient). The resource is accepted for future-proofing
    (e.g., shared inbox visibility rules).
    """

    type: str  # "workspace", "customer", "thread", "meeting", etc.
    id: str
    workspace_id: str  # Always required for membership lookup


# Action sets for role-based checks
OWNER_ACTIONS = {
    Action.MANAGE_BILLING,
    Action.DELETE_WORKSPACE,
    Action.TRANSFER_OWNERSHIP,
}

ADMIN_ACTIONS = {
    Action.INVITE_MEMBER,
    Action.REMOVE_MEMBER,
    Action.CHANGE_ROLE,
    Action.EDIT_WORKSPACE_SETTINGS,
    Action.MANAGE_INTEGRATIONS,
    Action.VIEW_BILLING,
    Action.VIEW_TEAM,
}


def _is_owner(role: str) -> bool:
    """Check if role is owner."""
    return role == "owner"


def _is_admin_or_higher(role: str) -> bool:
    """Check if role is admin or owner."""
    return role in ("owner", "admin")


def _is_member_or_higher(role: str) -> bool:
    """Check if role is a valid workspace role (member, admin, or owner)."""
    return role in ("owner", "admin", "member")


def can_access(
    user_role: str | None,
    action: Action,
    resource: Resource | None = None,
    *,
    target_user_id: str | None = None,
    target_role: str | None = None,
) -> bool:
    """
    Single entry point for all permission checks.

    Args:
        user_role: The user's role in the workspace (owner/admin/member or None)
        action: The action being attempted
        resource: Optional resource being accessed (for future visibility rules)
        target_user_id: For member management, the target user's ID
        target_role: For role changes, the target role

    Returns:
        True if allowed

    Raises:
        PermissionDenied: If access denied with reason
    """
    # No role means not a workspace member
    if user_role is None:
        raise PermissionDenied(action.value, "Not a workspace member")

    # Validate role is a known role
    if not _is_member_or_higher(user_role):
        raise PermissionDenied(action.value, f"Invalid role: {user_role}")

    # PATH 1: Owner-only actions
    if action in OWNER_ACTIONS:
        if not _is_owner(user_role):
            raise PermissionDenied(
                action.value,
                "Only workspace owner can perform this action"
            )
        return True

    # PATH 2: Admin actions
    if action in ADMIN_ACTIONS:
        if not _is_admin_or_higher(user_role):
            raise PermissionDenied(
                action.value,
                "Admin or owner role required"
            )

        # Special rules for member management
        if action == Action.REMOVE_MEMBER:
            # Admin cannot remove owner or other admins
            if target_role and not _is_owner(user_role):
                if target_role in ("owner", "admin"):
                    raise PermissionDenied(
                        action.value,
                        "Admin cannot remove owner or other admins"
                    )

        if action == Action.CHANGE_ROLE:
            # Admin cannot change anyone to/from owner
            if not _is_owner(user_role):
                if target_role == "owner":
                    raise PermissionDenied(
                        action.value,
                        "Only owner can promote to owner"
                    )
            # No one can demote owner (except via transfer)
            if target_role == "owner":
                raise PermissionDenied(
                    action.value,
                    "Cannot change owner role directly. Use ownership transfer."
                )

        return True

    # PATH 3: Customer-data actions - membership is sufficient
    # Resource is accepted but not consulted (future-proofing for shared inbox)
    return True


def check_can_remove_member(
    user_role: str,
    target_role: str,
) -> bool:
    """
    Specific check for member removal permission.

    Rules:
    - Owner can remove anyone except themselves
    - Admin can remove members, but not owner or other admins
    - Member cannot remove anyone
    """
    return can_access(
        user_role,
        Action.REMOVE_MEMBER,
        target_role=target_role,
    )


def check_can_change_role(
    user_role: str,
    current_role: str,
    new_role: str,
) -> bool:
    """
    Specific check for role change permission.

    Rules:
    - Owner can change any role (except their own to non-owner)
    - Admin can change member<->admin for non-owners
    - Admin cannot promote/demote to/from owner
    - Member cannot change roles
    """
    # Cannot change owner's role
    if current_role == "owner":
        raise PermissionDenied(
            "change_role",
            "Cannot change owner's role. Use ownership transfer instead."
        )

    # Check new role isn't owner (only via transfer)
    if new_role == "owner":
        raise PermissionDenied(
            "change_role",
            "Cannot promote to owner. Use ownership transfer instead."
        )

    return can_access(
        user_role,
        Action.CHANGE_ROLE,
        target_role=new_role,
    )


def check_can_invite(user_role: str, invite_role: str) -> bool:
    """
    Check if user can send invitation for a given role.

    Rules:
    - Owner can invite as admin or member
    - Admin can invite as admin or member
    - Member cannot invite
    - No one can invite as owner (ownership is at creation)
    """
    if invite_role == "owner":
        raise PermissionDenied(
            "invite_member",
            "Cannot invite as owner. Owner role is set at workspace creation."
        )

    if invite_role not in ("admin", "member"):
        raise PermissionDenied(
            "invite_member",
            f"Invalid role for invitation: {invite_role}"
        )

    return can_access(user_role, Action.INVITE_MEMBER)

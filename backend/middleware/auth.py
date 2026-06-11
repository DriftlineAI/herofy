"""
Firebase Authentication Middleware
Verifies Firebase ID tokens and extracts user information.
"""

from typing import Optional
from dataclasses import dataclass

import firebase_admin
from firebase_admin import auth, credentials
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from core.logging import get_logger
from config import settings
from db.dataconnect_client import set_context_impersonation

logger = get_logger("auth")

# HTTP Bearer token extractor
security = HTTPBearer(auto_error=False)

# Firebase app instance (initialized once)
_firebase_app: Optional[firebase_admin.App] = None


@dataclass
class FirebaseUser:
    """Authenticated user from Firebase token."""
    uid: str
    email: Optional[str] = None
    email_verified: bool = False
    name: Optional[str] = None
    picture: Optional[str] = None
    # Custom claims from Firebase
    workspace_id: Optional[str] = None
    role: Optional[str] = None
    # True when the Firebase token's sign-in provider is "anonymous" (demo sandbox users).
    is_anonymous: bool = False


def init_firebase() -> None:
    """
    Initialize Firebase Admin SDK.

    Uses Application Default Credentials (ADC) in production,
    or a service account JSON file in development.
    """
    global _firebase_app

    if _firebase_app is not None:
        return

    try:
        if settings.firebase_credentials_path:
            # Use explicit service account file
            cred = credentials.Certificate(settings.firebase_credentials_path)
            _firebase_app = firebase_admin.initialize_app(cred, {
                "projectId": settings.firebase_project_id,
            })
            logger.info("firebase_initialized", method="service_account")
        else:
            # Use Application Default Credentials (ADC)
            # This works in GCP environments or with GOOGLE_APPLICATION_CREDENTIALS env var
            _firebase_app = firebase_admin.initialize_app(options={
                "projectId": settings.firebase_project_id,
            })
            logger.info("firebase_initialized", method="application_default_credentials")

    except Exception as e:
        logger.error("firebase_init_failed", error=str(e))
        raise


def verify_token(token: str) -> dict:
    """
    Verify a Firebase ID token.

    Args:
        token: The Firebase ID token from the client

    Returns:
        Decoded token claims

    Raises:
        HTTPException: If token is invalid or expired
    """
    if _firebase_app is None:
        init_firebase()

    try:
        decoded = auth.verify_id_token(token)
        return decoded
    except auth.ExpiredIdTokenError:
        logger.warning("token_expired")
        raise HTTPException(status_code=401, detail="Token expired")
    except auth.RevokedIdTokenError:
        logger.warning("token_revoked")
        raise HTTPException(status_code=401, detail="Token revoked")
    except auth.InvalidIdTokenError as e:
        logger.warning("token_invalid", error=str(e))
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        logger.error("token_verification_failed", error=str(e))
        raise HTTPException(status_code=401, detail="Authentication failed")


def _reject_anon_unless_demo_allowed(decoded: dict, request: Optional[Request]) -> None:
    """Reject anonymous Firebase tokens unless DEMO_ENABLED.

    On the demo deployment (DEMO_ENABLED=true — the per-visitor disposable sandbox) the anonymous
    user IS the expected visitor and needs the full app, so we let them through here. The real
    per-workspace boundary is enforced downstream on every meaningful route by
    require_workspace_access (REST) and @check (DataConnect), which confine each visitor to the
    workspace they were provisioned into. With DEMO_ENABLED off (prod), anonymous tokens are
    rejected everywhere — anonymous auth has no legitimate use there.
    """
    provider = (decoded.get("firebase") or {}).get("sign_in_provider")
    if provider != "anonymous" or settings.demo_enabled:
        return
    path = request.url.path if request is not None else ""
    logger.warning("anonymous_auth_rejected", path=path, demo_enabled=settings.demo_enabled)
    raise HTTPException(status_code=403, detail="Anonymous authentication is not permitted")


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> FirebaseUser:
    """
    FastAPI dependency to get the current authenticated user.

    Reads the Firebase ID token from the Authorization header, or falls back
    to X-Firebase-ID-Token. The fallback exists because Firebase Hosting
    replaces the Authorization header with its own OIDC token when proxying
    to authenticated Cloud Run services, so the client must duplicate the
    token in a header Hosting leaves alone.
    """
    token: Optional[str] = credentials.credentials if credentials else None
    if not token:
        token = request.headers.get("X-Firebase-ID-Token")

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    decoded = verify_token(token)
    _reject_anon_unless_demo_allowed(decoded, request)

    # Extract user info from token
    user = FirebaseUser(
        uid=decoded["uid"],
        email=decoded.get("email"),
        email_verified=decoded.get("email_verified", False),
        name=decoded.get("name"),
        picture=decoded.get("picture"),
        # Custom claims (set via Firebase Admin SDK)
        workspace_id=decoded.get("workspace_id"),
        role=decoded.get("role"),
        is_anonymous=(decoded.get("firebase") or {}).get("sign_in_provider") == "anonymous",
    )

    # Run this request's admin-surface @check(auth.uid) ops AS this user (a member of the workspaces
    # they act on). NO_ACCESS ops are unaffected — the client only impersonates auth.uid ops.
    set_context_impersonation(user.uid)
    logger.debug("user_authenticated", uid=user.uid, email=user.email)
    return user


async def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[FirebaseUser]:
    """
    FastAPI dependency to optionally get the current user.
    Returns None if no token provided (doesn't raise error).

    Usage:
        @app.get("/public-or-private")
        async def route(user: Optional[FirebaseUser] = Depends(get_optional_user)):
            if user:
                return {"message": f"Hello {user.email}"}
            return {"message": "Hello guest"}
    """
    if credentials is None:
        return None

    try:
        token = credentials.credentials
        decoded = verify_token(token)
        _reject_anon_unless_demo_allowed(decoded, request)
        user = FirebaseUser(
            uid=decoded["uid"],
            email=decoded.get("email"),
            email_verified=decoded.get("email_verified", False),
            name=decoded.get("name"),
            picture=decoded.get("picture"),
            workspace_id=decoded.get("workspace_id"),
            role=decoded.get("role"),
            is_anonymous=(decoded.get("firebase") or {}).get("sign_in_provider") == "anonymous",
        )
        set_context_impersonation(user.uid)
        return user
    except HTTPException as exc:
        # Invalid/expired token (401) → treat as "no user". But an explicit anonymous-auth
        # rejection (403 from the demo guard) must propagate, not be silently downgraded to None.
        if exc.status_code == 403:
            raise
        return None


def require_workspace_access(workspace_id_param: str = "workspace_id"):
    """
    Factory for a dependency that verifies user has access to a workspace.

    This dependency:
    1. Verifies user is a member of the workspace
    2. Attaches the user's role and workspace_id to the FirebaseUser object

    Usage:
        @app.get("/workspaces/{workspace_id}/data")
        async def get_data(
            workspace_id: str,
            user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
        ):
            # User is verified to have access to workspace_id
            # user.role contains their role (owner/admin/member)
            # user.workspace_id contains the workspace ID
            return {"data": "..."}

    Args:
        workspace_id_param: Name of the path parameter containing workspace ID

    Returns:
        Dependency function that verifies workspace access and attaches role
    """
    async def verify_access(
        request: Request,
        user: FirebaseUser = Depends(get_current_user),
    ) -> FirebaseUser:
        # Get workspace_id from path parameters first, then query parameters
        workspace_id = request.path_params.get(workspace_id_param)
        if not workspace_id:
            workspace_id = request.query_params.get(workspace_id_param)

        if not workspace_id:
            raise HTTPException(status_code=400, detail="Workspace ID required")

        # Check workspace membership and get role
        from db.dataconnect_client import get_dataconnect_client
        dc = get_dataconnect_client()

        result = await dc.execute_query(
            "CheckWorkspaceMembership",
            {"workspaceId": workspace_id, "userId": user.uid},
        )

        members = result.get("workspaceMembers", [])
        if not members:
            logger.warning(
                "workspace_access_denied",
                uid=user.uid,
                workspace_id=workspace_id,
            )
            raise HTTPException(
                status_code=403,
                detail="Access denied to this workspace",
            )

        # Attach role and workspace_id to user for downstream permission checks
        user.role = members[0].get("role")
        user.workspace_id = workspace_id

        logger.debug(
            "workspace_access_granted",
            uid=user.uid,
            workspace_id=workspace_id,
            role=user.role,
        )
        return user

    return verify_access

"""Middleware module - FastAPI middleware and dependencies."""

from .auth import (
    init_firebase,
    get_current_user,
    require_workspace_access,
    FirebaseUser,
)

__all__ = [
    "init_firebase",
    "get_current_user",
    "require_workspace_access",
    "FirebaseUser",
]

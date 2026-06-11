"""Routes module - FastAPI route handlers."""

from .health import router as health_router
from .agents import router as agents_router, workspace_agents_router
from .webhooks import router as webhooks_router
from .ai import router as ai_router
from .integrations import router as integrations_router
from .waitlist import router as waitlist_router
from .team import router as team_router, public_router as team_public_router
from .enrichment import router as enrichment_router
from .sidekick import router as sidekick_router
from .customers import router as customers_router
from .setup import router as setup_router
from .test import router as test_router
from .sync import router as sync_router
from .auth import router as auth_router

__all__ = [
    "auth_router",
    "health_router",
    "agents_router",
    "workspace_agents_router",
    "webhooks_router",
    "ai_router",
    "integrations_router",
    "waitlist_router",
    "team_router",
    "team_public_router",
    "enrichment_router",
    "sidekick_router",
    "customers_router",
    "setup_router",
    "test_router",
    "sync_router",
]

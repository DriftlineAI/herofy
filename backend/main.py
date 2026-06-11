"""
Herofy Python Backend
FastAPI server for autonomous agents using Google ADK
"""

# Load .env BEFORE any other imports so FIRESTORE_EMULATOR_HOST is available
# when firebase_admin checks os.environ at import time
from dotenv import load_dotenv
load_dotenv()

import asyncio
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from core.errors import HerofyError, ValidationError
from core.permissions import PermissionDenied
from core.logging import configure_logging, get_logger
from db.client import init_db_client, close_db_client
from db.dataconnect_client import init_dataconnect_client, close_dataconnect_client
from middleware.auth import init_firebase
from routes import health_router, agents_router, workspace_agents_router, webhooks_router, ai_router, integrations_router, waitlist_router, team_router, team_public_router, enrichment_router, sidekick_router, customers_router, setup_router, test_router, sync_router, auth_router
from services import init_firestore_service

# Configure logging first
configure_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info(
        "server_starting",
        port=settings.port,
        environment=settings.environment,
    )

    # Initialize database connections
    # During migration, we run BOTH asyncpg and DataConnect in parallel
    # This allows gradual migration of services while keeping OAuth flows working

    # Always initialize asyncpg (needed for OAuth flows that haven't been migrated)
    try:
        await init_db_client(settings.database_url)
        logger.info("database_initialized", mode="asyncpg")
    except Exception as e:
        logger.error("database_init_failed", error=str(e))
        # If we're running in DataConnect mode, asyncpg is expected to be unavailable
        # (we only need it for legacy migrations/OAuth paths later).
        if settings.is_production and not settings.use_dataconnect:
            sys.exit(1)

        logger.warning(
            "asyncpg_init_failed_continuing",
            error=str(e),
            use_dataconnect=settings.use_dataconnect,
        )

    # Also initialize DataConnect if enabled
    if settings.use_dataconnect:
        try:
            await init_dataconnect_client()
            logger.info("dataconnect_initialized", mode="firebase_data_connect")
        except Exception as e:
            logger.error("dataconnect_init_failed", error=str(e))
            if settings.is_production:
                sys.exit(1)
            else:
                logger.warning("dataconnect_init_failed_continuing", error=str(e))

    # Initialize Firebase
    try:
        init_firebase()
        logger.info("firebase_initialized")
    except Exception as e:
        logger.error("firebase_init_failed", error=str(e))
        # Firebase is optional in development
        if settings.is_production:
            sys.exit(1)

    # Initialize Firestore real-time service (depends on Firebase being initialized)
    try:
        init_firestore_service()
        logger.info("firestore_service_initialized")
    except Exception as e:
        logger.warning("firestore_service_init_failed", error=str(e))
        # Firestore is optional - real-time features will be disabled

    # Initialize Langfuse OTel tracing (no-op if LANGFUSE_SECRET_KEY is not set)
    from core.telemetry import setup_langfuse
    setup_langfuse()

    try:
        yield
    except asyncio.CancelledError:
        # Abrupt shutdown (Ctrl+C or --reload) cancels the ASGI lifespan task while
        # it's parked waiting for the shutdown message, throwing CancelledError in
        # here at the yield. Swallow it so it doesn't surface as an unhandled error
        # traceback; cleanup still runs in the finally below.
        logger.info("server_shutdown_interrupted")
    finally:
        # Shutdown — always run cleanup, even on cancellation, and never let a
        # failing close crash the shutdown sequence.
        logger.info("server_shutting_down")
        try:
            if settings.use_dataconnect:
                await close_dataconnect_client()
            else:
                await close_db_client()
            logger.info("database_closed")
        except asyncio.CancelledError:
            logger.warning("database_close_cancelled")
        except Exception as e:
            logger.warning("database_close_failed", error=str(e))


# Create FastAPI app
app = FastAPI(
    title="Herofy Python Backend",
    description="Autonomous agents for customer success workspace",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware - match Express configuration
origins = (
    [
        "https://herofy.ai",
        "https://www.herofy.ai",
        "https://demo.herofy.ai",
        # Same-origin in the normal Hosting setup (CORS never fires), but kept so the app
        # still works if VITE_PYTHON_URL ever targets the Cloud Run URL directly.
        "https://herofy-496505.web.app",
        "https://herofy-496505.firebaseapp.com",
    ]
    if settings.is_production
    else [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ]
)
origins += settings.cors_origins_extra

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Error Handlers
# =============================================================================


@app.exception_handler(HerofyError)
async def herofy_error_handler(request: Request, exc: HerofyError):
    """
    Convert Herofy exceptions to structured JSON responses.
    Mirrors Express error handling format.
    """
    status_code = 500

    if isinstance(exc, ValidationError):
        status_code = 400
    elif isinstance(exc, PermissionDenied):
        status_code = 403
    elif exc.code == "WORKSPACE_SCOPE_ERROR":
        status_code = 403
    elif exc.code == "AGENT_TIMEOUT":
        status_code = 504

    logger.error(
        "request_error",
        path=request.url.path,
        error_code=exc.code,
        error_message=exc.message,
    )

    return JSONResponse(
        status_code=status_code,
        content=exc.to_dict(),
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    """Catch-all for unexpected errors."""
    logger.exception(
        "unhandled_error",
        path=request.url.path,
        error=str(exc),
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "message": "Internal server error"
                if settings.is_production
                else str(exc),
                "code": "INTERNAL_ERROR",
            }
        },
    )


# =============================================================================
# Routes
# =============================================================================

# Health check routes (no prefix)
app.include_router(health_router)

# Agent routes
app.include_router(agents_router)

# Workspace-scoped agent routes (for frontend HITL UI)
app.include_router(workspace_agents_router, prefix="/api")

# Webhook routes (for external integrations)
app.include_router(webhooks_router)

# AI routes (draft generation, plan regeneration)
app.include_router(ai_router, prefix="/api")

# OAuth integrations routes (no /api prefix - these are user-facing OAuth flows)
app.include_router(integrations_router)

# Waitlist route (public, no auth required)
app.include_router(waitlist_router)

# Team management routes (workspace-scoped)
app.include_router(team_router, prefix="/api")

# Auth routes (custom-claims sync for Firestore tenant isolation)
app.include_router(auth_router, prefix="/api")

# Team invitation routes (public endpoints for accepting invitations)
app.include_router(team_public_router, prefix="/api")

# Customer enrichment routes
app.include_router(enrichment_router, prefix="/api")

# Sidekick routes (HITL questions, tips, agent progress)
app.include_router(sidekick_router, prefix="/api")

# Customer routes (health scoring, etc.)
app.include_router(customers_router, prefix="/api")

# Setup routes (workspace setup completion)
app.include_router(setup_router, prefix="/api")

# Test routes (development only - simulate webhooks)
if not settings.is_production:
    app.include_router(test_router, prefix="/test")

# Sync routes (polling and watermark management)
app.include_router(sync_router, prefix="/sync")

# Orchestrator routes (net-new, side-by-side). MOUNT-ONLY feature flag: when
# ORCHESTRATION_ENABLED is False (default) this is never imported or registered,
# so the backend behaves exactly as today and handoff_auto is untouched.
if settings.orchestration_enabled:
    from routes.orchestrator import router as orchestrator_router

    app.include_router(orchestrator_router)
    logger.info("orchestrator_routes_mounted", flag="ORCHESTRATION_ENABLED")

# Demo provisioning routes (per-visitor anonymous sandbox). MOUNT-ONLY feature flag: when
# DEMO_ENABLED is False (default) this is never imported or registered, and anonymous tokens are
# rejected everywhere (middleware/auth.py).
if settings.demo_enabled:
    from routes.demo import router as demo_router

    app.include_router(demo_router)
    logger.info("demo_routes_mounted", flag="DEMO_ENABLED")


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
    )

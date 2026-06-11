"""
ADK runtime service factories (Session / Memory / Artifact).

Adopted from day 1 so nothing has to be glued in later. Dev uses the in-memory
implementations; production swaps these single factories for DatabaseSessionService
(on the existing Postgres `DATABASE_URL`), a Vertex/RAG MemoryService, and
GcsArtifactService — without touching any caller.

Process-level singletons: the session service in particular must be shared so a
task's session is visible across the drain loop and the agent run within a process.
"""

from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.adk.memory import BaseMemoryService, InMemoryMemoryService
from google.adk.artifacts import BaseArtifactService, InMemoryArtifactService

from config import get_settings
from core.logging import get_logger

logger = get_logger("OrchestratorRuntime")

_session_service: BaseSessionService | None = None
_memory_service: BaseMemoryService | None = None
_artifact_service: BaseArtifactService | None = None


def get_session_service() -> BaseSessionService:
    """Durable-by-contract session store. Dev: InMemory. Prod: DatabaseSessionService.

    Swap point: when `settings.is_production`, construct
    `DatabaseSessionService(db_url=settings.database_url)` here. Sessions then
    survive restarts and pair with the durable AgentTask queue for restart-safe HITL.
    """
    global _session_service
    if _session_service is None:
        # NOTE: prod swap goes here (DatabaseSessionService on DATABASE_URL).
        _session_service = InMemorySessionService()
        logger.info("orchestrator_session_service_init", impl="InMemorySessionService")
    return _session_service


def get_memory_service() -> BaseMemoryService:
    """Long-term memory. Dev: InMemory. Prod: Vertex Memory Bank / pgvector RAG.

    The orchestrator's `memory_recall` tool is DataConnect-backed for the demo;
    this service is wired for `add_session_to_memory` (Phase 2 write path) and the
    eventual semantic-recall accelerator.
    """
    global _memory_service
    if _memory_service is None:
        _memory_service = InMemoryMemoryService()
        logger.info("orchestrator_memory_service_init", impl="InMemoryMemoryService")
    return _memory_service


def get_artifact_service() -> BaseArtifactService:
    """Versioned artifact blobs (briefs, strategy docs). Dev: InMemory. Prod: GCS."""
    global _artifact_service
    if _artifact_service is None:
        _artifact_service = InMemoryArtifactService()
        logger.info("orchestrator_artifact_service_init", impl="InMemoryArtifactService")
    return _artifact_service


def reset_services() -> None:
    """Drop singletons (tests / hot-reload)."""
    global _session_service, _memory_service, _artifact_service
    _session_service = None
    _memory_service = None
    _artifact_service = None

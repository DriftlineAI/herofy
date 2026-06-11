"""Services module - business logic layer."""

from .handoff_service import HandoffService
from .handoff_service_dc import HandoffServiceDC
from .plan_service import PlanService
from .plan_service_dc import PlanServiceDC
from .customer_service import CustomerService
from .customer_service_dc import CustomerServiceDC
from .agent_run_service import AgentRunService
from .integration_service import IntegrationService
from .integration_service_dc import IntegrationServiceDC
from .notion_service import NotionService
from .notion_service_dc import NotionServiceDC
from .hitl_answers import HITLAnswerService, extract_answers_from_run
from .sidekick_service import SidekickService
from .health_scoring_service import HealthScoringService, HealthWeights
from .firestore_service import FirestoreRealtimeService, get_firestore_service, init_firestore_service
from .customer_insights_service import (
    CustomerInsightsService,
    CustomerInsight,
    PortfolioSnapshot,
    refresh_customer_insight,
    refresh_all_customer_insights,
)
from .customer_factory import CustomerFactory
# PollService is not needed - use SyncOrchestrator which routes through SignalWatcherEventProcessor
# SetupService is not imported here to avoid circular imports
# Import it directly: from services.setup_service import SetupService

from config import get_settings


def get_integration_service(workspace_id: str):
    """
    Factory function to get the appropriate IntegrationService.

    Returns IntegrationServiceDC if use_dataconnect is enabled,
    otherwise returns the legacy IntegrationService.
    """
    settings = get_settings()

    if settings.use_dataconnect:
        from db.dataconnect_client import get_dataconnect_client
        dc = get_dataconnect_client()
        return IntegrationServiceDC(dc, workspace_id)
    else:
        from db.client import get_db_client
        db = get_db_client()
        return IntegrationService(db, workspace_id)


def get_notion_service(workspace_id: str):
    """
    Factory function to get the appropriate NotionService.

    Returns NotionServiceDC if use_dataconnect is enabled,
    otherwise returns the legacy NotionService.
    """
    settings = get_settings()

    if settings.use_dataconnect:
        from db.dataconnect_client import get_dataconnect_client
        dc = get_dataconnect_client()
        return NotionServiceDC(dc, workspace_id)
    else:
        from db.client import get_db_client
        db = get_db_client()
        return NotionService(db, workspace_id)


def get_customer_service(workspace_id: str):
    """
    Factory function to get the appropriate CustomerService.

    Returns CustomerServiceDC if use_dataconnect is enabled,
    otherwise returns the legacy CustomerService.
    """
    settings = get_settings()

    if settings.use_dataconnect:
        from db.dataconnect_client import get_dataconnect_client
        dc = get_dataconnect_client()
        return CustomerServiceDC(dc, workspace_id)
    else:
        from db.client import get_db_client
        db = get_db_client()
        return CustomerService(db, workspace_id)


def get_handoff_service(workspace_id: str):
    """
    Factory function to get the appropriate HandoffService.

    Returns HandoffServiceDC if use_dataconnect is enabled,
    otherwise returns the legacy HandoffService.
    """
    settings = get_settings()

    if settings.use_dataconnect:
        from db.dataconnect_client import get_dataconnect_client
        dc = get_dataconnect_client()
        return HandoffServiceDC(dc, workspace_id)
    else:
        from db.client import get_db_client
        db = get_db_client()
        return HandoffService(db, workspace_id)


def get_plan_service(workspace_id: str):
    """
    Factory function to get the appropriate PlanService.

    Returns PlanServiceDC if use_dataconnect is enabled,
    otherwise returns the legacy PlanService.
    """
    settings = get_settings()

    if settings.use_dataconnect:
        from db.dataconnect_client import get_dataconnect_client
        dc = get_dataconnect_client()
        return PlanServiceDC(dc, workspace_id)
    else:
        from db.client import get_db_client
        db = get_db_client()
        return PlanService(db, workspace_id)


__all__ = [
    "HandoffService",
    "HandoffServiceDC",
    "PlanService",
    "PlanServiceDC",
    "CustomerService",
    "CustomerServiceDC",
    "AgentRunService",
    "IntegrationService",
    "IntegrationServiceDC",
    "NotionService",
    "NotionServiceDC",
    "HITLAnswerService",
    "extract_answers_from_run",
    "get_integration_service",
    "get_notion_service",
    "get_customer_service",
    "get_handoff_service",
    "get_plan_service",
    "SidekickService",
    "HealthScoringService",
    "HealthWeights",
    "FirestoreRealtimeService",
    "get_firestore_service",
    "init_firestore_service",
    "CustomerInsightsService",
    "CustomerInsight",
    "PortfolioSnapshot",
    "refresh_customer_insight",
    "refresh_all_customer_insights",
    "CustomerFactory",
]

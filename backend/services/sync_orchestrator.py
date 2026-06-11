"""
Sync Orchestrator Service

Coordinates polling across all integrations using the unified ingestion pipeline.

Architecture:
1. Event Emitters poll sources (Notion, Gmail, Slack) and produce ChangeEvents
2. Orchestrator collects events, persists them, and feeds to SignalWatcherEventProcessor
3. EventProcessor classifies and routes events (sync fields, invoke agents, etc.)
4. Watermarks are updated after successful processing
"""

from typing import Any
from datetime import datetime, timezone
from uuid import UUID
import json

from core.logging import get_logger
from core.types import IntegrationType
from core.errors import IntegrationNotConfiguredError, IntegrationAuthError
from core.events import ChangeEvent
from config import settings
from db.client import DatabaseClient, get_db_client

from services.event_emitters import (
    NotionEventEmitter,
    GmailEventEmitter,
    SlackEventEmitter,
)
from agents.signal_watcher_unified.event_processor import SignalWatcherEventProcessor

logger = get_logger("SyncOrchestrator")


class SyncOrchestrator:
    """
    Orchestrates polling and syncing across all workspace integrations.

    Uses the unified ingestion pipeline:
    1. Event emitters produce ChangeEvents from each source
    2. Events are persisted for auditing and dedup
    3. SignalWatcherEventProcessor classifies and routes events
    4. Watermarks are updated after successful processing

    This replaces direct NotionService.poll_and_sync() calls with
    a unified event-driven architecture.
    """

    def __init__(self, db: DatabaseClient | None = None):
        self.db = db or get_db_client()

    async def run_poll_for_integration(
        self,
        integration_type: str,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Run poll for a specific integration type.

        If workspace_id is provided, polls only that workspace.
        Otherwise, polls all workspaces with active integration.

        Args:
            integration_type: The integration to poll (notion, gmail, etc.)
            workspace_id: Optional specific workspace to poll

        Returns:
            Summary of poll results
        """
        results = {
            "integration_type": integration_type,
            "workspaces_polled": 0,
            "new_items": 0,
            "errors": [],
        }

        if workspace_id:
            # Poll single workspace
            try:
                workspace_result = await self._poll_workspace_integration(
                    workspace_id,
                    integration_type,
                )
                results["workspaces_polled"] = 1
                results["new_items"] = workspace_result.get("new_items", 0)
            except Exception as e:
                results["errors"].append({
                    "workspace_id": workspace_id,
                    "error": str(e),
                })
        else:
            # Poll all workspaces with this integration
            workspaces = await self._get_workspaces_with_integration(integration_type)
            results["workspaces_polled"] = len(workspaces)

            for ws_id in workspaces:
                try:
                    workspace_result = await self._poll_workspace_integration(
                        ws_id,
                        integration_type,
                    )
                    results["new_items"] += workspace_result.get("new_items", 0)
                except Exception as e:
                    logger.error(
                        "poll_workspace_failed",
                        workspace_id=ws_id,
                        integration_type=integration_type,
                        error=str(e),
                    )
                    results["errors"].append({
                        "workspace_id": ws_id,
                        "error": str(e),
                    })

        logger.info(
            "poll_completed",
            integration_type=integration_type,
            workspaces_polled=results["workspaces_polled"],
            new_items=results["new_items"],
            error_count=len(results["errors"]),
        )

        return results

    async def _poll_workspace_integration(
        self,
        workspace_id: str,
        integration_type: str,
    ) -> dict[str, Any]:
        """
        Poll a specific workspace's integration.

        Args:
            workspace_id: Workspace ID
            integration_type: Integration type

        Returns:
            Poll results for this workspace
        """
        logger.info(
            "polling_workspace",
            workspace_id=workspace_id,
            integration_type=integration_type,
        )

        if integration_type == "notion":
            return await self._poll_notion(workspace_id)
        elif integration_type == "gmail":
            return await self._poll_gmail(workspace_id)
        elif integration_type == "slack":
            return await self._poll_slack(workspace_id)
        else:
            logger.warning(
                "unknown_integration_type",
                integration_type=integration_type,
            )
            return {"new_items": 0}

    async def _poll_notion(self, workspace_id: str) -> dict[str, Any]:
        """
        Poll Notion for changes using the unified event emitter.

        Args:
            workspace_id: Workspace ID

        Returns:
            Poll results
        """
        try:
            # Create emitter and processor
            emitter = NotionEventEmitter(workspace_id, self.db)
            processor = SignalWatcherEventProcessor(workspace_id, self.db)

            # Emit events from source
            events = await emitter.poll_and_emit()

            if not events:
                logger.debug(
                    "no_notion_events",
                    workspace_id=workspace_id,
                )
                return {"new_items": 0}

            # Persist events for auditing
            await self._persist_events(events)

            # Process events through classification cascade
            processed_events = await processor.process_events(events)

            # Update watermark
            if processed_events:
                max_occurred = max(e.occurred_at for e in processed_events)
                await emitter.update_watermark(max_occurred)

            # Persist processing results
            for event in processed_events:
                await processor.persist_event(event)

            # Update integration status
            await self._mark_integration_success(workspace_id, IntegrationType.NOTION)

            # Count artifacts
            agent_runs = sum(len(e.artifacts_created.agent_runs) for e in processed_events)

            return {
                "new_items": len(events),
                "processed": len(processed_events),
                "triggered_agents": agent_runs,
            }

        except IntegrationNotConfiguredError:
            logger.info(
                "integration_not_configured",
                workspace_id=workspace_id,
                integration_type="notion",
            )
            return {"new_items": 0}

        except IntegrationAuthError as e:
            await self._mark_integration_error(
                workspace_id,
                IntegrationType.NOTION,
                str(e),
            )
            raise

    async def _poll_gmail(self, workspace_id: str) -> dict[str, Any]:
        """
        Poll Gmail for new messages using the unified event emitter.

        Args:
            workspace_id: Workspace ID

        Returns:
            Poll results
        """
        try:
            # Create emitter and processor
            emitter = GmailEventEmitter(workspace_id, self.db)
            processor = SignalWatcherEventProcessor(workspace_id, self.db)

            # Emit events from source
            events = await emitter.poll_and_emit()

            if not events:
                logger.debug(
                    "no_gmail_events",
                    workspace_id=workspace_id,
                )
                return {"new_items": 0}

            # Persist events for auditing
            await self._persist_events(events)

            # Process events through classification cascade
            processed_events = await processor.process_events(events)

            # Update watermark
            if processed_events:
                max_occurred = max(e.occurred_at for e in processed_events)
                await emitter.update_watermark(max_occurred)

            # Persist processing results
            for event in processed_events:
                await processor.persist_event(event)

            # Update integration status
            await self._mark_integration_success(workspace_id, IntegrationType.GMAIL)

            return {
                "new_items": len(events),
                "processed": len(processed_events),
            }

        except IntegrationNotConfiguredError:
            logger.info(
                "integration_not_configured",
                workspace_id=workspace_id,
                integration_type="gmail",
            )
            return {"new_items": 0}

        except IntegrationAuthError as e:
            await self._mark_integration_error(
                workspace_id,
                IntegrationType.GMAIL,
                str(e),
            )
            raise

    async def _poll_slack(self, workspace_id: str) -> dict[str, Any]:
        """
        Poll Slack for new messages using the unified event emitter.

        Args:
            workspace_id: Workspace ID

        Returns:
            Poll results
        """
        try:
            # Create emitter and processor
            emitter = SlackEventEmitter(workspace_id, self.db)
            processor = SignalWatcherEventProcessor(workspace_id, self.db)

            # Emit events from source
            events = await emitter.poll_and_emit()

            if not events:
                logger.debug(
                    "no_slack_events",
                    workspace_id=workspace_id,
                )
                return {"new_items": 0}

            # Persist events for auditing
            await self._persist_events(events)

            # Process events through classification cascade
            processed_events = await processor.process_events(events)

            # Update watermark
            if processed_events:
                max_occurred = max(e.occurred_at for e in processed_events)
                await emitter.update_watermark(max_occurred)

            # Persist processing results
            for event in processed_events:
                await processor.persist_event(event)

            # Update integration status
            await self._mark_integration_success(workspace_id, IntegrationType.SLACK)

            return {
                "new_items": len(events),
                "processed": len(processed_events),
            }

        except IntegrationNotConfiguredError:
            logger.info(
                "integration_not_configured",
                workspace_id=workspace_id,
                integration_type="slack",
            )
            return {"new_items": 0}

        except IntegrationAuthError as e:
            await self._mark_integration_error(
                workspace_id,
                IntegrationType.SLACK,
                str(e),
            )
            raise

    async def _persist_events(self, events: list[ChangeEvent]) -> None:
        """
        Persist ChangeEvents to the database.

        Events are stored for auditing and deduplication.
        The fingerprint + workspace_id combination prevents duplicates.

        Args:
            events: List of ChangeEvents to persist
        """
        from db.dataconnect_client import get_dataconnect_client

        dc = get_dataconnect_client()

        for event in events:
            try:
                # Check if event already exists by fingerprint
                existing = await dc.execute_query(
                    "GetChangeEventByFingerprint",
                    {
                        "workspaceId": str(event.workspace_id),
                        "fingerprint": event.fingerprint,
                    },
                )

                if existing.get("changeEvents", []):
                    # Event already exists, skip
                    logger.debug(
                        "event_already_exists",
                        event_id=str(event.id),
                        fingerprint=event.fingerprint[:16],
                    )
                    continue

                # Create the event (id is auto-generated by the database)
                await dc.execute_mutation(
                    "CreateChangeEvent",
                    {
                        "workspaceId": str(event.workspace_id),
                        "source": event.source.value,
                        "sourceEventType": event.source_event_type,
                        "sourceRecordId": event.source_record_id,
                        "fingerprint": event.fingerprint,
                        "customerId": str(event.customer_id) if event.customer_id else None,
                        "rawPayload": json.dumps(event.raw_payload),
                        "occurredAt": event.occurred_at.isoformat(),
                    },
                )

                logger.debug(
                    "event_persisted",
                    event_id=str(event.id),
                    source=event.source.value,
                )

            except Exception as e:
                # Log but don't fail - duplicate fingerprint is expected
                if "duplicate" not in str(e).lower() and "conflict" not in str(e).lower():
                    logger.warning(
                        "event_persistence_failed",
                        event_id=str(event.id),
                        error=str(e),
                    )

    async def _get_workspaces_with_integration(
        self,
        integration_type: str,
    ) -> list[str]:
        """
        Get all workspace IDs with an active integration of the given type.

        Args:
            integration_type: Integration type

        Returns:
            List of workspace IDs
        """
        if settings.use_dataconnect:
            from db.dataconnect_client import get_dataconnect_client

            dc = get_dataconnect_client()

            # Query all active integrations of this type
            result = await dc.execute_query(
                "GetActiveIntegrationWorkspaces",
                {"integrationType": integration_type},
            )

            # Extract workspace IDs from nested structure
            # Response format: { workspace: { id: "uuid" }, ... }
            workspace_ids = []
            for ws in result.get("workspaceIntegrations", []):
                workspace = ws.get("workspace", {})
                if isinstance(workspace, dict) and workspace.get("id"):
                    workspace_ids.append(workspace["id"])
            return workspace_ids
        else:
            from db.client import get_db_client

            db = get_db_client()

            rows = await db.query_all(
                """
                SELECT DISTINCT workspace_id
                FROM workspace_integrations
                WHERE integration_type = $1 AND status = 'active'
                """,
                [integration_type],
            )

            return [row["workspace_id"] for row in rows]

    async def _mark_integration_success(
        self,
        workspace_id: str,
        integration_type: IntegrationType,
    ) -> None:
        """
        Mark integration sync as successful.

        Args:
            workspace_id: Workspace ID
            integration_type: Integration type
        """
        if settings.use_dataconnect:
            from db.dataconnect_client import get_dataconnect_client

            dc = get_dataconnect_client()
            await dc.execute_mutation(
                "RecordIntegrationSync",
                {
                    "workspaceId": workspace_id,
                    "integrationType": integration_type.value,
                },
            )
        else:
            from db.client import get_db_client

            db = get_db_client()
            await db.execute(
                """
                UPDATE workspace_integrations
                SET last_sync_at = NOW(), last_error = NULL, error_count = 0
                WHERE workspace_id = $1 AND integration_type = $2
                """,
                [workspace_id, integration_type.value],
            )

        logger.debug(
            "integration_sync_recorded",
            workspace_id=workspace_id,
            integration_type=integration_type.value,
        )

    async def _mark_integration_error(
        self,
        workspace_id: str,
        integration_type: IntegrationType,
        error: str,
    ) -> None:
        """
        Mark integration as errored.

        Args:
            workspace_id: Workspace ID
            integration_type: Integration type
            error: Error message
        """
        if settings.use_dataconnect:
            from db.dataconnect_client import get_dataconnect_client

            dc = get_dataconnect_client()
            await dc.execute_mutation(
                "UpdateIntegrationStatus",
                {
                    "workspaceId": workspace_id,
                    "integrationType": integration_type.value,
                    "status": "error",
                    "lastError": error[:500],  # Truncate long errors
                    "errorCount": 1,  # Would need to increment in practice
                },
            )
        else:
            from db.client import get_db_client

            db = get_db_client()
            await db.execute(
                """
                UPDATE workspace_integrations
                SET status = 'error',
                    last_error = $3,
                    error_count = error_count + 1
                WHERE workspace_id = $1 AND integration_type = $2
                """,
                [workspace_id, integration_type.value, error[:500]],
            )

        logger.warning(
            "integration_marked_error",
            workspace_id=workspace_id,
            integration_type=integration_type.value,
            error=error,
        )


    async def poll_all_integrations(
        self,
        workspace_id: str,
    ) -> dict[str, Any]:
        """
        Poll all active integrations for a workspace.

        Polls Notion, Gmail, and Slack in sequence.
        Use this for scheduled polling of a workspace.

        Args:
            workspace_id: Workspace ID

        Returns:
            Combined results from all integrations
        """
        results = {
            "workspace_id": workspace_id,
            "integrations_polled": 0,
            "total_events": 0,
            "total_processed": 0,
            "errors": [],
        }

        # Get active integrations for this workspace
        active_integrations = await self._get_active_integrations(workspace_id)

        for integration_type in active_integrations:
            try:
                poll_result = await self._poll_workspace_integration(
                    workspace_id,
                    integration_type,
                )
                results["integrations_polled"] += 1
                results["total_events"] += poll_result.get("new_items", 0)
                results["total_processed"] += poll_result.get("processed", 0)

            except Exception as e:
                results["errors"].append({
                    "integration_type": integration_type,
                    "error": str(e),
                })

        logger.info(
            "workspace_poll_completed",
            workspace_id=workspace_id,
            integrations=results["integrations_polled"],
            events=results["total_events"],
            processed=results["total_processed"],
            errors=len(results["errors"]),
        )

        return results

    async def _get_active_integrations(self, workspace_id: str) -> list[str]:
        """
        Get list of active integration types for a workspace.

        Args:
            workspace_id: Workspace ID

        Returns:
            List of integration type strings
        """
        from db.dataconnect_client import get_dataconnect_client

        dc = get_dataconnect_client()

        result = await dc.execute_query(
            "GetWorkspaceIntegrations",
            {"workspaceId": workspace_id},
        )

        # Filter to active integrations and extract types
        integrations = []
        for integration in result.get("workspaceIntegrations", []):
            if integration.get("status") == "active":
                integrations.append(integration.get("integrationType"))
        return integrations


# Module-level singleton
_orchestrator: SyncOrchestrator | None = None


def get_sync_orchestrator(db: DatabaseClient | None = None) -> SyncOrchestrator:
    """Get or create sync orchestrator singleton."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = SyncOrchestrator(db)
    return _orchestrator

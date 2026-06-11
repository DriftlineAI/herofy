"""
Firestore Real-time Service

Pushes real-time updates to Firestore for frontend subscriptions.
Used for streaming progress during:
- Customer classification in setup flow
- Agent execution status
- Workspace notification counts

This service writes to Firestore, which the frontend subscribes to
via onSnapshot() for live updates.
"""

from typing import Any
import firebase_admin
from firebase_admin import firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

from core.logging import get_logger
from config import get_settings

logger = get_logger("FirestoreRealtimeService")


def _normalize_uuid(uuid_str: str) -> str:
    """
    Normalize UUID to standard format with dashes.

    Ensures consistent document IDs in Firestore regardless of
    whether the input has dashes or not.

    Args:
        uuid_str: UUID string with or without dashes

    Returns:
        UUID string in format xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    """
    # Remove any existing dashes
    clean = uuid_str.replace("-", "")
    # Re-insert dashes in standard positions
    if len(clean) == 32:
        return f"{clean[:8]}-{clean[8:12]}-{clean[12:16]}-{clean[16:20]}-{clean[20:]}"
    # If not a valid UUID length, return as-is
    return uuid_str


class FirestoreRealtimeService:
    """
    Service for pushing real-time updates to Firestore.

    Collections:
    - setup_progress/{workspaceId} - Customer classification progress
    - agent_status/{runId} - Agent execution status
    - notifications/{workspaceId} - Workspace notification counts
    """

    _instance: "FirestoreRealtimeService | None" = None
    _db: Any = None

    def __init__(self):
        """Initialize the Firestore client."""
        self.settings = get_settings()
        # run_id -> dashed workspaceId, so agent_status docs can be tenant-isolated in security rules
        # without threading workspace_id through every status-update call site. Resolved once per run.
        self._run_workspace: dict[str, str] = {}
        self._ensure_db()

    async def _workspace_for_run(self, run_id: str) -> str | None:
        """Resolve (and cache) the dashed workspaceId that owns an agent run. Best-effort."""
        cached = self._run_workspace.get(run_id)
        if cached:
            return cached
        try:
            from db.dataconnect_client import get_dataconnect_client
            dc = get_dataconnect_client()
            data = await dc.execute_query("GetAgentRunWorkspace", {"id": run_id})
            ws = (((data or {}).get("agentRun") or {}).get("workspace") or {}).get("id")
            if ws:
                ws = _normalize_uuid(ws)
                self._run_workspace[run_id] = ws
                return ws
        except Exception as e:  # noqa: BLE001 - status writes are best-effort, never raise
            logger.debug("agent_status_workspace_lookup_failed", run_id=run_id, error=str(e))
        return None

    def _ensure_db(self):
        """Ensure Firestore client is initialized."""
        import os

        if FirestoreRealtimeService._db is None:
            try:
                # Check emulator configuration in development
                emulator_host = os.environ.get("FIRESTORE_EMULATOR_HOST")
                if self.settings.is_development:
                    if emulator_host:
                        logger.info(
                            "firestore_emulator_configured",
                            emulator_host=emulator_host,
                        )
                    else:
                        logger.warning(
                            "firestore_emulator_not_configured",
                            message="FIRESTORE_EMULATOR_HOST not set. "
                            "Real-time UI updates will NOT work. "
                            "Add FIRESTORE_EMULATOR_HOST=localhost:8181 to backend/.env",
                        )

                # Firebase Admin should already be initialized by auth middleware
                FirestoreRealtimeService._db = firestore.client()
                logger.info("firestore_client_initialized", emulator_host=emulator_host)
            except Exception as e:
                logger.error("firestore_client_init_failed", error=str(e))
                raise

    @property
    def db(self):
        """Get the Firestore client."""
        self._ensure_db()
        return FirestoreRealtimeService._db

    # =========================================================================
    # Setup Progress (Customer Classification)
    # =========================================================================

    async def update_setup_progress(
        self,
        workspace_id: str,
        customer_id: str,
        status: str,
        progress: dict[str, Any],
    ) -> None:
        """
        Update classification progress for a customer during setup.

        Args:
            workspace_id: The workspace ID
            customer_id: The customer being classified
            status: 'pending' | 'reading' | 'classified' | 'error'
            progress: Additional progress data (step, progress_pct, etc.)
        """
        try:
            normalized_id = _normalize_uuid(workspace_id)
            doc_ref = self.db.collection('setup_progress').document(normalized_id)

            # Use dot notation to update nested field
            update_data = {
                f'customers.{customer_id}': {
                    'status': status,
                    **progress,
                },
                'updated_at': SERVER_TIMESTAMP,
            }

            doc_ref.set(update_data, merge=True)

            logger.debug(
                "setup_progress_updated",
                workspace_id=workspace_id,
                customer_id=customer_id,
                status=status,
            )
        except Exception as e:
            logger.error(
                "setup_progress_update_failed",
                workspace_id=workspace_id,
                customer_id=customer_id,
                error=str(e),
            )
            # Don't raise - real-time updates are best-effort

    async def clear_setup_progress(self, workspace_id: str) -> None:
        """
        Clear all setup progress for a workspace.

        Called when setup is complete or when re-running setup.
        """
        try:
            normalized_id = _normalize_uuid(workspace_id)
            doc_ref = self.db.collection('setup_progress').document(normalized_id)
            doc_ref.delete()
            logger.info("setup_progress_cleared", workspace_id=workspace_id)
        except Exception as e:
            logger.error(
                "setup_progress_clear_failed",
                workspace_id=workspace_id,
                error=str(e),
            )

    # =========================================================================
    # Agent Status
    # =========================================================================

    async def update_agent_status(
        self,
        run_id: str,
        status: str,
        step: str,
        progress_pct: int,
        message: str,
        customer_id: str | None = None,
        customer_name: str | None = None,
    ) -> None:
        """
        Update agent run status for real-time tracking.

        Args:
            run_id: The agent run ID
            status: 'starting' | 'running' | 'paused' | 'waiting_for_input' | 'completed' | 'failed'
            step: Current step description
            progress_pct: Progress percentage (0-100)
            message: Human-readable status message
            customer_id: Optional customer ID being processed
            customer_name: Optional customer name for display
        """
        try:
            normalized_id = _normalize_uuid(run_id)
            doc_ref = self.db.collection('agent_status').document(normalized_id)

            update_data = {
                'status': status,
                'current_step': step,
                'progress_pct': progress_pct,
                'message': message,
                'updated_at': SERVER_TIMESTAMP,
            }

            if customer_id:
                update_data['customer_id'] = customer_id
            if customer_name:
                update_data['customer_name'] = customer_name

            # Stamp the owning workspace so security rules can tenant-isolate reads
            # (isMember(resource.data.workspaceId)). Resolved+cached per run; best-effort.
            workspace_id = await self._workspace_for_run(run_id)
            if workspace_id:
                update_data['workspaceId'] = workspace_id

            doc_ref.set(update_data, merge=True)

            logger.debug(
                "agent_status_updated",
                run_id=run_id,
                status=status,
                step=step,
                progress_pct=progress_pct,
            )
        except Exception as e:
            logger.error(
                "agent_status_update_failed",
                run_id=run_id,
                error=str(e),
            )

    async def append_agent_output(
        self,
        run_id: str,
        agent_name: str,
        text: str | None = None,
        function_calls: list[str] | None = None,
        kind: str = "llm",
    ) -> None:
        """Append one agent/LLM output to agent_status/{runId}/outputs (for the Lab trace view).

        Best-effort and never raises into the agent flow. Ordered by created_at on the client.
        """
        try:
            normalized_id = _normalize_uuid(run_id)
            col = (
                self.db.collection('agent_status')
                .document(normalized_id)
                .collection('outputs')
            )
            # Cap generously so large tool results (e.g. investigate_account's customer+history
            # JSON) stay WHOLE and still parse as JSON for pretty-printing. Firestore allows ~1MB
            # per field; 30k is plenty and well under that.
            col.add({
                'agent_name': agent_name,
                'kind': kind,
                'text': (text or '')[:30000],
                'function_calls': function_calls or [],
                'created_at': SERVER_TIMESTAMP,
            })
        except Exception as e:  # streaming is non-fatal
            logger.warning("agent_output_append_failed", run_id=run_id, error=str(e))

    async def append_step(
        self,
        run_id: str,
        step: str,
        status: str,
        progress_pct: int | None = None,
    ) -> None:
        """Append one step transition to agent_status/{runId}/steps (append-only, reliable).

        The agent_status doc itself is overwritten many times/second, so rapid step changes get
        coalesced by client onSnapshot listeners — the Lab can miss steps (e.g. a play root). This
        ordered log captures every transition so the Lab can reconstruct the true path. Best-effort.
        """
        try:
            normalized_id = _normalize_uuid(run_id)
            col = (
                self.db.collection('agent_status')
                .document(normalized_id)
                .collection('steps')
            )
            col.add({
                'step': step,
                'status': status,
                'progress_pct': progress_pct,
                'created_at': SERVER_TIMESTAMP,
            })
        except Exception as e:  # streaming is non-fatal
            logger.warning("agent_step_append_failed", run_id=run_id, error=str(e))

    async def clear_agent_status(self, run_id: str) -> None:
        """Clear agent status after completion or timeout."""
        try:
            normalized_id = _normalize_uuid(run_id)
            doc_ref = self.db.collection('agent_status').document(normalized_id)
            doc_ref.delete()
            logger.debug("agent_status_cleared", run_id=run_id)
        except Exception as e:
            logger.error(
                "agent_status_clear_failed",
                run_id=run_id,
                error=str(e),
            )

    # =========================================================================
    # Workspace Notifications
    # =========================================================================

    async def update_workspace_notifications(
        self,
        workspace_id: str,
        **counts: int,
    ) -> None:
        """
        Update workspace notification counts.

        Args:
            workspace_id: The workspace ID
            **counts: Key-value pairs of notification counts
                - today_count: Items in Today queue
                - unread_conversations: Unread conversation count
                - sidekick_questions: Pending Sidekick questions
                - agent_runs_active: Active agent runs
        """
        try:
            # Normalize workspace ID to ensure consistent document IDs
            normalized_id = _normalize_uuid(workspace_id)
            doc_ref = self.db.collection('notifications').document(normalized_id)

            update_data = {
                **counts,
                'updated_at': SERVER_TIMESTAMP,
            }

            doc_ref.set(update_data, merge=True)

            logger.info(
                "workspace_notifications_updated",
                workspace_id=workspace_id,
                counts=counts,
            )
        except Exception as e:
            logger.error(
                "workspace_notifications_update_failed",
                workspace_id=workspace_id,
                error=str(e),
            )

    async def refresh_today_count(self, workspace_id: str) -> int:
        """
        Recalculate and push the today queue count.

        Called when needs are created, resolved, or snoozed.
        Queries DataConnect for accurate count and pushes to Firestore.

        Returns:
            The refreshed count.
        """
        try:
            from db.dataconnect_client import get_dataconnect_client

            dc = get_dataconnect_client()
            # Get unresolved, unsnoozed needs count
            today_items = await dc.get_today_queue(workspace_id=workspace_id)
            today_count = len(today_items) if today_items else 0

            await self.update_workspace_notifications(
                workspace_id=workspace_id,
                today_count=today_count,
            )

            logger.info(
                "today_count_refreshed",
                workspace_id=workspace_id,
                count=today_count,
            )
            return today_count
        except Exception as e:
            logger.error(
                "today_count_refresh_failed",
                workspace_id=workspace_id,
                error=str(e),
            )
            return 0

    async def refresh_sidekick_count(self, workspace_id: str) -> int:
        """
        Recalculate and push the sidekick questions count.

        Counts unresolved needs of type sidekick_question.
        This aligns with the Sidekick page which queries these needs.

        Returns:
            The refreshed count.
        """
        try:
            from db.dataconnect_client import get_dataconnect_client

            dc = get_dataconnect_client()
            # Get sidekick_question needs (unresolved)
            result = await dc.execute_query(
                "GetSidekickQuestionNeeds",
                {"workspaceId": workspace_id},
            )
            needs = result.get("needs", [])
            sidekick_count = len(needs)

            await self.update_workspace_notifications(
                workspace_id=workspace_id,
                sidekick_questions=sidekick_count,
            )

            logger.info(
                "sidekick_count_refreshed",
                workspace_id=workspace_id,
                count=sidekick_count,
            )
            return sidekick_count
        except Exception as e:
            logger.error(
                "sidekick_count_refresh_failed",
                workspace_id=workspace_id,
                error=str(e),
            )
            return 0

    async def refresh_all_counts(self, workspace_id: str) -> dict[str, int]:
        """
        Refresh all notification counts from the database.

        Use this to resync Firestore with the actual database state,
        e.g., after a database wipe or when counts get out of sync.

        Returns:
            Dict with all refreshed counts.
        """
        today_count = await self.refresh_today_count(workspace_id)
        sidekick_count = await self.refresh_sidekick_count(workspace_id)

        logger.info(
            "all_counts_refreshed",
            workspace_id=workspace_id,
            today_count=today_count,
            sidekick_count=sidekick_count,
        )

        return {
            "today_count": today_count,
            "sidekick_questions": sidekick_count,
        }

    async def notify_need_created(
        self,
        workspace_id: str,
        need_id: str,
        need_type: str,
        customer_name: str | None = None,
    ) -> None:
        """
        Notify that a new need was created.

        Refreshes today count and sidekick count (if sidekick_question).
        Can trigger UI animations for new items.
        """
        try:
            # Refresh the today count
            await self.refresh_today_count(workspace_id)

            # Also refresh sidekick count if this is a sidekick question
            if need_type == "sidekick_question":
                await self.refresh_sidekick_count(workspace_id)

            # Also push a "last_event" for potential animations
            normalized_id = _normalize_uuid(workspace_id)
            doc_ref = self.db.collection('notifications').document(normalized_id)
            doc_ref.set({
                'last_event': {
                    'type': 'need_created',
                    'need_id': need_id,
                    'need_type': need_type,
                    'customer_name': customer_name,
                    'timestamp': SERVER_TIMESTAMP,
                },
            }, merge=True)

            logger.debug(
                "need_created_notification",
                workspace_id=workspace_id,
                need_id=need_id,
                need_type=need_type,
            )
        except Exception as e:
            logger.error(
                "need_created_notification_failed",
                workspace_id=workspace_id,
                need_id=need_id,
                error=str(e),
            )

    async def notify_need_resolved(
        self,
        workspace_id: str,
        need_id: str,
    ) -> None:
        """
        Notify that a need was resolved.

        Refreshes today count and sidekick count (in case it was a sidekick_question).
        """
        try:
            await self.refresh_today_count(workspace_id)
            # Also refresh sidekick count (simpler than checking need type)
            await self.refresh_sidekick_count(workspace_id)

            logger.debug(
                "need_resolved_notification",
                workspace_id=workspace_id,
                need_id=need_id,
            )
        except Exception as e:
            logger.error(
                "need_resolved_notification_failed",
                workspace_id=workspace_id,
                need_id=need_id,
                error=str(e),
            )

    # =========================================================================
    # Conversations Real-Time
    # =========================================================================

    async def set_active_run(self, workspace_id: str, run_id: str | None) -> None:
        """
        Track the currently-running orchestrator agent run.

        Sets active_run_id on the workspace notifications doc so the frontend
        can subscribe to agent_status/{run_id} for live progress display.
        Pass run_id=None to clear after the run finishes.
        """
        try:
            normalized_id = _normalize_uuid(workspace_id)
            doc_ref = self.db.collection('notifications').document(normalized_id)
            doc_ref.set({'active_run_id': run_id}, merge=True)
            logger.debug(
                "active_run_set",
                workspace_id=workspace_id,
                run_id=run_id,
            )
        except Exception as e:
            logger.error(
                "set_active_run_failed",
                workspace_id=workspace_id,
                run_id=run_id,
                error=str(e),
            )

    async def notify_conversation_updated(
        self,
        workspace_id: str,
        thread_id: str | None = None,
        interaction_count: int = 1,
        channel: str | None = None,
    ) -> None:
        """
        Notify that conversations were updated (new messages arrived).

        Increments a counter that the frontend watches to trigger refetch.
        Uses the same pattern as notify_need_created() for Today Queue.

        Args:
            workspace_id: The workspace ID
            thread_id: Optional thread ID for future granular updates
            interaction_count: Number of new interactions created
            channel: Source channel (email, slack, etc.)
        """
        try:
            from google.cloud.firestore_v1 import Increment

            normalized_id = _normalize_uuid(workspace_id)
            doc_ref = self.db.collection('notifications').document(normalized_id)

            # Increment conversation update counter (matches today_count pattern)
            doc_ref.set({
                'conversations_count': Increment(interaction_count),
                'updated_at': SERVER_TIMESTAMP,
                'last_conversation_event': {
                    'type': 'new_messages',
                    'thread_id': thread_id,
                    'interaction_count': interaction_count,
                    'channel': channel,
                    'timestamp': SERVER_TIMESTAMP,
                },
            }, merge=True)

            logger.info(
                "conversation_update_notification",
                workspace_id=workspace_id,
                thread_id=thread_id,
                interaction_count=interaction_count,
                channel=channel,
            )
        except Exception as e:
            logger.error(
                "conversation_update_notification_failed",
                workspace_id=workspace_id,
                error=str(e),
            )


# Singleton accessor
_firestore_service: FirestoreRealtimeService | None = None


def get_firestore_service() -> FirestoreRealtimeService:
    """Get the singleton FirestoreRealtimeService instance."""
    global _firestore_service
    if _firestore_service is None:
        _firestore_service = FirestoreRealtimeService()
    return _firestore_service


def init_firestore_service() -> FirestoreRealtimeService:
    """Initialize the FirestoreRealtimeService (called at startup)."""
    global _firestore_service
    _firestore_service = FirestoreRealtimeService()
    logger.info("firestore_service_initialized")
    return _firestore_service

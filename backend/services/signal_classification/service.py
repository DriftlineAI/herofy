"""
Signal Classification Service

Main orchestrator for LLM-based signal classification.
Coordinates classification, signal creation, need auto-creation, and commitment extraction.
"""

from uuid import uuid4, UUID
import hashlib
from typing import Any

from core.logging import get_logger
from core.events import ChangeEvent
from db.dataconnect_client import get_dataconnect_client
from services.firestore_service import get_firestore_service

from .llm_classifier import LLMSignalClassifier
from .signal_to_need_mapper import SignalToNeedMapper
from .models import SignalWithNeed, ContentClassificationOutput, SignalClassification

logger = get_logger("SignalClassificationService")


class SignalClassificationService:
    """
    Main service for LLM-based signal classification.

    Orchestrates:
    1. LLM classification of content
    2. Signal creation in database (with deduplication)
    3. Need auto-creation (if confidence > threshold)
    4. Commitment extraction

    Usage:
        service = SignalClassificationService(workspace_id)
        results = await service.classify_and_process(event, customer_id)
    """

    def __init__(
        self,
        workspace_id: str,
        classifier: LLMSignalClassifier | None = None,
        mapper: SignalToNeedMapper | None = None,
    ):
        """
        Initialize service.

        Args:
            workspace_id: Workspace UUID string
            classifier: Optional custom classifier (for testing)
            mapper: Optional custom mapper (for testing)
        """
        self.workspace_id = workspace_id
        self.classifier = classifier or LLMSignalClassifier()
        self.mapper = mapper or SignalToNeedMapper()

    async def classify_and_process(
        self,
        event: ChangeEvent,
        customer_id: UUID,
    ) -> list[SignalWithNeed]:
        """
        Classify event content and create Signals/Needs.

        Flow:
        1. Fetch customer context (name, lifecycle, recent signals)
        2. Call LLM classifier
        3. For each signal:
           - Check deduplication
           - Create Signal record
           - If confidence > 0.7: Create Need
        4. Extract commitments separately

        Args:
            event: ChangeEvent to classify
            customer_id: Customer UUID

        Returns:
            List of created signals with optional needs
        """
        # Step 1: Fetch customer context
        customer_context = await self._fetch_customer_context(customer_id)

        # Step 2: LLM classification
        classification = await self.classifier.classify_content(
            event=event,
            customer_context=customer_context,
        )

        # Early exit if no signals detected and low confidence
        if not classification.signals and classification.overall_confidence < 0.5:
            logger.info(
                "no_significant_signals",
                event_id=str(event.id),
                customer_id=str(customer_id),
                confidence=classification.overall_confidence,
            )
            return []

        # Fetch customer goals for observation linking
        customer_goals = await self._fetch_customer_goals(customer_id)

        # Step 3: Process each signal
        results = []
        best_signal_for_observation = None
        for signal_data in classification.signals:
            result = await self._process_signal(
                event=event,
                customer_id=customer_id,
                signal_data=signal_data,
                suggested_need_type=classification.suggested_need_type,
            )
            if result:
                results.append(result)
                # Track highest-confidence signal with evidence for observation
                if signal_data.evidence_text:
                    if best_signal_for_observation is None or signal_data.confidence > best_signal_for_observation.confidence:
                        best_signal_for_observation = signal_data

        # Create ONE goal observation for the best signal (not one per signal)
        if customer_goals and best_signal_for_observation:
            await self._create_goal_observation(
                customer_id=customer_id,
                goals=customer_goals,
                signal_data=best_signal_for_observation,
                event=event,
            )

        # Step 4: Process commitments
        if classification.commitments:
            await self._process_commitments(
                customer_id=customer_id,
                commitments=classification.commitments,
            )

        logger.info(
            "classification_processing_completed",
            event_id=str(event.id),
            customer_id=str(customer_id),
            signals_created=len(results),
            needs_created=sum(1 for r in results if r.need_id),
        )

        # Step 5: Trigger health score recalculation if signals were created
        if results:
            await self._update_customer_health(customer_id)

        return results

    async def _fetch_customer_context(self, customer_id: UUID) -> dict[str, Any]:
        """
        Fetch customer data for LLM context.

        Args:
            customer_id: Customer UUID

        Returns:
            Dict with name, lifecycle, tier, recent_signals
        """
        dc = get_dataconnect_client()

        # Get customer info
        result = await dc.execute_query(
            "GetCustomerPublic",
            {"id": str(customer_id)},
        )

        customer = result.get("customer") or {}

        # Get recent signals (last 7 days)
        from datetime import datetime, timedelta, timezone
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=7)

        try:
            signals_result = await dc.execute_query(
                "GetRecentSignalsForCustomer",
                {
                    "workspaceId": self.workspace_id,
                    "customerId": str(customer_id),
                    "since": cutoff_date.isoformat(),
                },
            )
            recent_signals = signals_result.get("signals", [])
        except Exception as e:
            logger.debug(
                "recent_signals_fetch_failed",
                customer_id=str(customer_id),
                error=str(e),
            )
            recent_signals = []

        return {
            "name": customer.get("name", "Unknown"),
            "lifecycle": customer.get("lifecycle", "unknown"),
            "tier": customer.get("tier", "unknown"),
            "recent_signals": recent_signals[:5],
        }

    async def _fetch_customer_goals(self, customer_id: UUID) -> list[dict]:
        """
        Fetch active goals for a customer.

        Args:
            customer_id: Customer UUID

        Returns:
            List of goal dicts with id and text
        """
        dc = get_dataconnect_client()

        try:
            result = await dc.execute_query(
                "GetCustomerGoals",
                {
                    "customerId": str(customer_id),
                    "workspaceId": self.workspace_id,
                },
            )
            goals = result.get("goals", [])
            # Filter to active goals only
            return [g for g in goals if g.get("status") == "active"]
        except Exception as e:
            logger.debug(
                "customer_goals_fetch_failed",
                customer_id=str(customer_id),
                error=str(e),
            )
            return []

    async def _process_signal(
        self,
        event: ChangeEvent,
        customer_id: UUID,
        signal_data: SignalClassification,
        suggested_need_type: str | None,
    ) -> SignalWithNeed | None:
        """
        Process a single signal: create Signal and optionally Need.

        Args:
            event: Source ChangeEvent
            customer_id: Customer UUID
            signal_data: Classified signal
            suggested_need_type: LLM's suggested need type

        Returns:
            SignalWithNeed if created, None if skipped
        """
        # Check confidence threshold for signal creation
        if not self.mapper.should_create_signal(signal_data):
            logger.debug(
                "signal_below_threshold",
                confidence=signal_data.confidence,
                threshold=self.mapper.CONFIDENCE_THRESHOLD_SIGNAL,
            )
            return None

        # Check deduplication
        fingerprint = self._compute_signal_fingerprint(event, signal_data)
        if await self._is_duplicate_signal(fingerprint):
            logger.debug(
                "duplicate_signal_skipped",
                event_id=str(event.id),
                fingerprint=fingerprint[:16],
            )
            return None

        # Create Signal record
        signal_id = await self._create_signal(
            customer_id=customer_id,
            event_id=event.id,
            signal_data=signal_data,
            fingerprint=fingerprint,
        )

        # Check if Need should be created
        need_id = None
        need_type = None

        if self.mapper.should_create_need(signal_data):
            # Skip positive signals unless very high confidence
            if not self.mapper.should_skip_positive_signal(signal_data):
                need_type = self.mapper.map_signal_to_need_type(
                    signal=signal_data,
                    suggested_need_type=suggested_need_type,
                )

                priority = self.mapper.determine_need_priority(signal_data, need_type)

                need_id = await self._create_need(
                    customer_id=customer_id,
                    need_type=need_type,
                    signal_sentence=signal_data.sentence,
                    priority=priority,
                    confidence=signal_data.confidence,
                )

                logger.info(
                    "need_auto_created",
                    signal_id=str(signal_id),
                    need_id=str(need_id),
                    need_type=need_type,
                    confidence=signal_data.confidence,
                )

        return SignalWithNeed(
            signal_id=signal_id,
            need_id=need_id,
            need_type=need_type,
            confidence=signal_data.confidence,
            signal_kind=signal_data.kind,
            signal_state=signal_data.state,
            signal_sentence=signal_data.sentence,
        )

    def _compute_signal_fingerprint(
        self,
        event: ChangeEvent,
        signal_data: SignalClassification,
    ) -> str:
        """
        Compute fingerprint for signal deduplication.

        Fingerprint based on:
        - Source and record ID
        - Signal kind
        - Evidence text (first 200 chars)

        Args:
            event: Source ChangeEvent
            signal_data: Classified signal

        Returns:
            SHA256 fingerprint string
        """
        components = [
            event.source.value,
            event.source_record_id,
            signal_data.kind,
            (signal_data.evidence_text or "")[:200],
        ]
        raw = "|".join(components)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def _is_duplicate_signal(self, fingerprint: str) -> bool:
        """
        Check if signal with this fingerprint already exists.

        Uses a 90-day window for deduplication.

        Args:
            fingerprint: Signal fingerprint

        Returns:
            True if duplicate exists
        """
        dc = get_dataconnect_client()

        try:
            result = await dc.execute_query(
                "GetSignalByFingerprint",
                {
                    "workspaceId": self.workspace_id,
                    "fingerprint": fingerprint,
                },
            )
            signals = result.get("signals", [])
            return len(signals) > 0
        except Exception as e:
            # If query fails, allow signal creation (fail open)
            logger.warning(
                "dedup_check_failed",
                fingerprint=fingerprint[:16],
                error=str(e),
            )
            return False

    async def _create_signal(
        self,
        customer_id: UUID,
        event_id: UUID,
        signal_data: SignalClassification,
        fingerprint: str,
    ) -> UUID:
        """
        Create Signal record in database.

        Args:
            customer_id: Customer UUID
            event_id: Source event UUID
            signal_data: Classified signal
            fingerprint: Deduplication fingerprint

        Returns:
            Created Signal UUID
        """
        dc = get_dataconnect_client()

        signal_id = uuid4()

        await dc.execute_mutation(
            "CreateSignalWithId",
            {
                "id": str(signal_id),
                "workspaceId": self.workspace_id,
                "customerId": str(customer_id),
                "kind": signal_data.kind,
                "state": signal_data.state,
                "sentence": signal_data.sentence,
                "evidenceText": signal_data.evidence_text,
                "model": self.classifier.model_name,
                "promptVersion": "signal-classification-v1",
                "inputsHash": fingerprint,
                "handbookVersionId": "00000000-0000-0000-0000-000000000000",  # Placeholder
            },
        )

        logger.debug(
            "signal_created",
            signal_id=str(signal_id),
            kind=signal_data.kind,
            state=signal_data.state,
            confidence=signal_data.confidence,
        )

        return signal_id

    async def _create_need(
        self,
        customer_id: UUID,
        need_type: str,
        signal_sentence: str,
        priority: int,
        confidence: float,
    ) -> UUID:
        """
        Create Need record in database.

        Args:
            customer_id: Customer UUID
            need_type: Type of need
            signal_sentence: One-line summary for headline
            priority: Priority rank (lower = more urgent)
            confidence: Classification confidence

        Returns:
            Created Need UUID
        """
        dc = get_dataconnect_client()

        need_id = uuid4()

        # Generate headline from signal sentence (truncate if needed)
        headline = signal_sentence[:120]

        await dc.execute_mutation(
            "CreateNeedWithId",
            {
                "id": str(need_id),
                "workspaceId": self.workspace_id,
                "customerId": str(customer_id),
                "type": need_type,
                "headline": headline,
                "priorityRank": priority,
                "agentReasoning": f"Auto-created from signal classification (confidence: {confidence:.0%})",
                # handbookVersionId is optional - omit for auto-classified needs
            },
        )

        logger.debug(
            "need_created",
            need_id=str(need_id),
            need_type=need_type,
            priority=priority,
        )

        # Push real-time notification to Firestore for Today queue updates
        try:
            firestore = get_firestore_service()
            await firestore.notify_need_created(
                workspace_id=self.workspace_id,
                need_id=str(need_id),
                need_type=need_type,
            )
        except Exception as notify_err:
            logger.warning("need_notification_failed", need_id=str(need_id), error=str(notify_err))

        return need_id

    async def _create_goal_observation(
        self,
        customer_id: UUID,
        goals: list[dict],
        signal_data: SignalClassification,
        event: ChangeEvent,
    ) -> None:
        """
        Create a GoalObservation linking a signal to a customer goal.

        Links the observation to the first active goal. In the future,
        could use semantic matching to find the most relevant goal.

        Args:
            customer_id: Customer UUID
            goals: List of active goals
            signal_data: The classified signal
            event: Source change event
        """
        if not goals:
            return

        dc = get_dataconnect_client()
        goal_id = goals[0]["id"]  # Link to first active goal

        # Generate fingerprint for deduplication
        fingerprint_input = f"{self.workspace_id}:{goal_id}:{signal_data.sentence}"
        fingerprint = hashlib.sha256(fingerprint_input.encode()).hexdigest()[:32]

        # Map signal state to confidence level
        confidence_map = {
            "ok": "high",
            "warn": "medium",
            "risk": "high",
        }
        confidence = confidence_map.get(signal_data.state, "medium")

        # Determine source type from event
        source_type_map = {
            "gmail": "email",
            "slack": "slack message",
            "notion": "document",
            "calendar": "meeting",
        }
        source_type = source_type_map.get(event.source.value, event.source.value)

        try:
            await dc.execute_mutation(
                "CreateGoalObservation",
                {
                    "workspaceId": self.workspace_id,
                    "customerId": str(customer_id),
                    "goalId": goal_id,
                    "text": signal_data.sentence,
                    "confidence": confidence,
                    "sourceType": source_type,
                    "sourceInteractionId": None,
                    "fingerprint": fingerprint,
                },
            )
            logger.info(
                "goal_observation_created_from_signal",
                customer_id=str(customer_id),
                goal_id=goal_id,
                observation_text=signal_data.sentence[:50],
            )
        except Exception as e:
            # Likely duplicate fingerprint, skip quietly
            logger.debug(
                "goal_observation_create_failed",
                customer_id=str(customer_id),
                goal_id=goal_id,
                error=str(e),
            )

    async def _process_commitments(
        self,
        customer_id: UUID,
        commitments: list,
    ) -> None:
        """
        Extract and create Commitment records.

        Args:
            customer_id: Customer UUID
            commitments: List of extracted commitments
        """
        dc = get_dataconnect_client()

        for commit in commitments:
            if commit.confidence < 0.6:
                continue  # Skip low-confidence commitments

            try:
                await dc.execute_mutation(
                    "CreateCommitment",
                    {
                        "workspaceId": self.workspace_id,
                        "customerId": str(customer_id),
                        "text": commit.what,
                        "side": commit.who,
                        "dueLabel": commit.due_date,  # Uses dueLabel not dueAt
                    },
                )

                logger.debug(
                    "commitment_created",
                    customer_id=str(customer_id),
                    who=commit.who,
                    what=commit.what[:50],
                )

            except Exception as e:
                logger.warning(
                    "commitment_creation_failed",
                    customer_id=str(customer_id),
                    error=str(e),
                )

    async def _update_customer_health(self, customer_id: UUID) -> None:
        """
        Trigger health score recalculation after signal creation.

        This ensures health scores are updated immediately when signals
        are created, rather than waiting for the signal watcher loop.

        Note: Failures here don't block signal creation - health updates
        are best-effort to ensure signal processing continues.
        """
        from services.health_scoring_service import HealthScoringService

        dc = get_dataconnect_client()
        health_service = HealthScoringService(dc, self.workspace_id)

        try:
            result = await health_service.calculate_health(
                str(customer_id),
                updated_by="system:signal_classification"
            )
            logger.info(
                "health_score_updated_after_signal_creation",
                customer_id=str(customer_id),
                health=result.health,
                score=result.score,
            )
        except Exception as e:
            # Log but don't fail - health updates are best-effort
            logger.warning(
                "health_score_update_failed",
                customer_id=str(customer_id),
                error=str(e),
            )

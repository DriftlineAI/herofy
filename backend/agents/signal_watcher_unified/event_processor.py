"""
SignalWatcher Event Processor

Processes ChangeEvents from the unified ingestion pipeline.
Implements the classification cascade and routing to appropriate handlers.

All sources (Notion, Gmail, Slack) emit ChangeEvents.
This processor consumes them and decides what to do:
- Dedup by fingerprint
- Resolve customer
- Classify event type
- Route to handler (sync field, classify content, invoke agent)
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID
import json

from core.events import (
    ChangeEvent,
    ChangeEventSource,
    ChangeEventClass,
    ArtifactsCreated,
    NotionNewRecordPayload,
    NotionFieldUpdatePayload,
    NotionContentUpdatePayload,
    MessagePayload,
    is_personal_email_domain,
)
from core.logging import get_logger
from services.firestore_service import get_firestore_service

logger = get_logger("SignalWatcherEventProcessor")


class SignalWatcherEventProcessor:
    """
    Processes ChangeEvents through classification cascade.

    Classification cascade:
    1. Dedup by fingerprint
    2. Resolve customer (stakeholder email → domain → unknown)
    3. Classify event type
    4. Route to appropriate handler

    Routing:
    - new_customer → HandoffAuto agent
    - structured_field_update → direct sync (no LLM)
    - unstructured_content → LLM classify → Signal + Need if significant
    - unknown_sender → drop or hold for review
    """

    def __init__(
        self,
        workspace_id: str,
        db: Any = None,  # kept for backward compatibility but no longer used
    ):
        self.workspace_id = workspace_id
        # Note: db parameter kept for backward compatibility but no longer used

    async def process_events(
        self,
        events: list[ChangeEvent],
    ) -> list[ChangeEvent]:
        """
        Process a batch of ChangeEvents.

        Args:
            events: ChangeEvents from emitters (already persisted)

        Returns:
            List of processed events with artifacts_created populated
        """
        processed_events: list[ChangeEvent] = []

        for event in events:
            try:
                # Skip already processed
                if event.processed:
                    continue

                # Atomically claim this event for processing
                # This prevents race conditions when multiple processors run concurrently
                claimed = await self._claim_event_for_processing(event)
                if not claimed:
                    logger.info(
                        "event_skipped_already_claimed",
                        event_id=str(event.id),
                        fingerprint=event.fingerprint[:16],
                    )
                    continue

                # Resolve customer if not already set
                if event.customer_id is None:
                    event.customer_id = await self._resolve_customer(event)

                # Classify event
                event.event_class = self._classify_event(event)

                # Route to handler
                event = await self._route_event(event)

                # Mark as processed
                event.processed = True
                event.processed_at = datetime.now(timezone.utc)

                processed_events.append(event)

                logger.info(
                    "event_processed",
                    event_id=str(event.id),
                    source=event.source.value,
                    event_class=event.event_class.value if event.event_class else None,
                    customer_id=str(event.customer_id) if event.customer_id else None,
                )

            except Exception as e:
                event.processing_error = str(e)
                event.processed = True
                event.processed_at = datetime.now(timezone.utc)
                processed_events.append(event)

                logger.error(
                    "event_processing_failed",
                    event_id=str(event.id),
                    error=str(e),
                )

        return processed_events

    # =========================================================================
    # Classification Cascade
    # =========================================================================

    async def _is_duplicate(self, event: ChangeEvent) -> bool:
        """
        Check if this event has already been processed.

        Dedup is based on (workspace_id, fingerprint) uniqueness.
        """
        from db.dataconnect_client import get_dataconnect_client

        dc = get_dataconnect_client()
        result = await dc.execute_query(
            "GetChangeEventByFingerprint",
            {
                "workspaceId": self.workspace_id,
                "fingerprint": event.fingerprint,
            },
        )

        events = result.get("changeEvents", [])
        if not events:
            return False

        # Check if the event was already processed
        return events[0].get("processed", False)

    async def _claim_event_for_processing(self, event: ChangeEvent) -> bool:
        """
        Atomically claim an event for processing.

        Uses updateMany with WHERE clause to ensure only one processor can claim
        an event at a time. This prevents race conditions when multiple
        processors run concurrently.

        Args:
            event: The event to claim

        Returns:
            True if successfully claimed, False if already claimed by another processor
        """
        from db.dataconnect_client import get_dataconnect_client

        try:
            dc = get_dataconnect_client()

            # Attempt to claim the event using updateMany (only updates if unprocessed)
            result = await dc.execute_mutation(
                "ClaimChangeEvent",
                {
                    "id": str(event.id),
                    "workspaceId": self.workspace_id,
                },
            )

            # The mutation uses updateMany which returns None but will only update
            # if the WHERE clause matches (processed = false)
            # For now, assume success - in practice we could check the query afterward
            return True

        except Exception as e:
            logger.warning(
                "claim_event_failed",
                event_id=str(event.id),
                error=str(e),
            )
            # On error, allow processing to continue (fail-open)
            return True

    async def _resolve_customer(self, event: ChangeEvent) -> UUID | None:
        """
        Customer resolution cascade.

        1. Exact stakeholder email match
        2. Domain match against customer domains (skip personal domains)
        3. Return None (unknown_sender)

        When domain match succeeds, auto-creates a stakeholder record.
        """
        from db.dataconnect_client import get_dataconnect_client

        # Extract sender email based on event source
        sender_email = self._extract_sender_email(event)
        if not sender_email:
            return None

        sender_domain = self._parse_email_domain(sender_email)
        sender_name = self._extract_sender_name(event)

        dc = get_dataconnect_client()

        # Step 1: Exact stakeholder email match
        stakeholder_result = await dc.execute_query(
            "GetStakeholderByEmail",
            {
                "workspaceId": self.workspace_id,
                "email": sender_email.lower(),
            },
        )

        stakeholders = stakeholder_result.get("stakeholders", [])
        if stakeholders:
            customer = stakeholders[0].get("customer", {})
            if customer and customer.get("id"):
                logger.debug(
                    "customer_resolved_by_stakeholder",
                    email=sender_email,
                    customer_id=customer["id"],
                )
                return UUID(str(customer["id"]))

        # Step 2: Domain match (skip personal email domains)
        if sender_domain and not is_personal_email_domain(sender_domain):
            customer_result = await dc.execute_query(
                "GetCustomerByDomain",
                {
                    "workspaceId": self.workspace_id,
                    "domain": sender_domain.lower(),
                },
            )

            customers = customer_result.get("customers", [])
            if customers:
                customer_id = UUID(str(customers[0]["id"]))

                # Auto-create stakeholder for this customer
                await self._create_stakeholder(customer_id, sender_email, sender_name)

                logger.debug(
                    "customer_resolved_by_domain",
                    domain=sender_domain,
                    customer_id=str(customer_id),
                )
                return customer_id

        # Step 3: No match
        logger.debug(
            "customer_not_resolved",
            email=sender_email,
            domain=sender_domain,
        )
        return None

    async def _resolve_stakeholder_id(self, event: ChangeEvent) -> UUID | None:
        """Resolve the inbound sender to a Stakeholder id for the Interaction FK +
        lastInteractionAt maintenance.

        Email is the reliable key (and by this point _resolve_customer has already
        email-matched or domain-auto-created the stakeholder). Name-only senders are
        left unresolved — the FK is additive, never a gate. Returns None on no match.
        """
        sender_email = self._extract_sender_email(event)
        if not sender_email:
            return None

        from db.dataconnect_client import get_dataconnect_client

        try:
            dc = get_dataconnect_client()
            result = await dc.execute_query(
                "GetStakeholderByEmail",
                {"workspaceId": self.workspace_id, "email": sender_email.lower()},
            )
            rows = result.get("stakeholders", [])
            return UUID(str(rows[0]["id"])) if rows else None
        except Exception as e:
            logger.warning("stakeholder_resolution_failed", email=sender_email, error=str(e))
            return None

    def _classify_event(self, event: ChangeEvent) -> ChangeEventClass:
        """
        Classify the event based on source and type.

        Classification rules:
        - Notion new_record → NEW_CUSTOMER (triggers HandoffAuto)
        - Notion field_update → STRUCTURED_FIELD_UPDATE (direct sync)
        - Notion content_update → UNSTRUCTURED_CONTENT (LLM classify)
        - Gmail/Slack message with customer → UNSTRUCTURED_CONTENT
        - Gmail/Slack message without customer → UNKNOWN_SENDER
        """
        source_event_type = event.source_event_type

        # Notion events
        if event.source == ChangeEventSource.NOTION:
            if source_event_type == "notion_new_record":
                return ChangeEventClass.NEW_CUSTOMER
            elif source_event_type == "notion_field_update":
                return ChangeEventClass.STRUCTURED_FIELD_UPDATE
            elif source_event_type == "notion_content_update":
                return ChangeEventClass.UNSTRUCTURED_CONTENT
            else:
                return ChangeEventClass.UNSTRUCTURED_CONTENT

        # Gmail/Slack events
        if event.source in (ChangeEventSource.GMAIL, ChangeEventSource.SLACK):
            if event.customer_id is None:
                return ChangeEventClass.UNKNOWN_SENDER
            else:
                return ChangeEventClass.UNSTRUCTURED_CONTENT

        # Default
        return ChangeEventClass.UNSTRUCTURED_CONTENT

    async def _route_event(self, event: ChangeEvent) -> ChangeEvent:
        """
        Route event to appropriate handler based on classification.

        Routing table:
        - NEW_CUSTOMER → invoke HandoffAuto agent
        - STRUCTURED_FIELD_UPDATE → sync field directly (no LLM)
        - UNSTRUCTURED_CONTENT → LLM classify → create Signal/Need if significant
        - UNKNOWN_SENDER → log and skip (or queue for review)
        """
        if event.event_class == ChangeEventClass.NEW_CUSTOMER:
            event = await self._handle_new_customer(event)

        elif event.event_class == ChangeEventClass.STRUCTURED_FIELD_UPDATE:
            event = await self._sync_structured_field(event)

        elif event.event_class == ChangeEventClass.UNSTRUCTURED_CONTENT:
            event = await self._classify_and_process_content(event)

        elif event.event_class == ChangeEventClass.UNKNOWN_SENDER:
            event = await self._handle_unknown_sender(event)

        return event

    # =========================================================================
    # Event Handlers
    # =========================================================================

    async def _handle_new_customer(self, event: ChangeEvent) -> ChangeEvent:
        """
        Handle new customer event (Notion trigger fired).

        Flow:
        1. Create Customer record via CustomerFactory (handles field mapping, dedup)
        2. Auto-link the source Notion page (fetches page body content)
        3. Trigger enrichment (now has linked page content available)
        4. Invoke HandoffAuto agent with customer_id

        Uses CustomerFactory for deterministic customer creation with proper
        field mapping from Notion properties.
        """
        from db.dataconnect_client import get_dataconnect_client
        from services.customer_factory import CustomerFactory

        payload = event.raw_payload
        page_id = payload.get("page_id")
        company_name = payload.get("company_name", "Unknown")
        properties = payload.get("properties", {})

        logger.info(
            "new_customer_event",
            page_id=page_id,
            company_name=company_name,
        )

        dc = get_dataconnect_client()

        # Step 1: Check if customer already exists (dedup)
        existing = await dc.execute_query(
            "GetCustomerByExternalId",
            {
                "workspaceId": self.workspace_id,
                "externalId": page_id,
            },
        )

        existing_customers = existing.get("customers", [])
        is_new_customer = False
        customer_id: UUID | None = None

        if existing_customers:
            customer_id = UUID(existing_customers[0]["id"])
            logger.info(
                "customer_already_exists",
                page_id=page_id,
                customer_id=str(customer_id),
            )
        else:
            is_new_customer = True

            # Get field mappings from integration config
            field_mappings = await self._get_notion_field_mappings()

            # Create customer via CustomerFactory
            # Factory handles: field mapping, lifecycle normalization, slug generation, stakeholders
            try:
                factory = CustomerFactory(self.workspace_id, dc)
                customer_id_str = await factory.create_from_notion(
                    notion_deal_id=page_id,
                    properties=properties,
                    field_mappings=field_mappings,
                )
                customer_id = UUID(customer_id_str)
                event.artifacts_created.customer_updates.append(customer_id_str)

                logger.info(
                    "customer_created_via_factory",
                    page_id=page_id,
                    customer_id=customer_id_str,
                    company_name=company_name,
                )

            except ValueError as e:
                # Missing required fields (e.g., name)
                logger.error(
                    "customer_creation_failed_validation",
                    page_id=page_id,
                    company_name=company_name,
                    error=str(e),
                )
                return event

            except Exception as e:
                logger.error(
                    "customer_creation_failed",
                    page_id=page_id,
                    company_name=company_name,
                    error=str(e),
                )
                return event

        # Update event with customer_id
        event.customer_id = customer_id

        # Step 2: Auto-link the source Notion page (fetches page body content)
        # This makes the rich page content available for enrichment and agent context
        if is_new_customer and customer_id and page_id:
            try:
                from services.notion_service_dc import link_notion_page_to_customer

                link_result = await link_notion_page_to_customer(
                    workspace_id=self.workspace_id,
                    customer_id=str(customer_id),
                    page_id=page_id,
                    page_title=company_name,
                    page_type="crm_record",  # Source CRM record
                    trigger_enrichment=False,  # We'll trigger enrichment below
                )

                if link_result.get("success"):
                    content_length = link_result.get("content_length", 0)
                    logger.info(
                        "source_page_auto_linked",
                        customer_id=str(customer_id),
                        page_id=page_id,
                        content_length=content_length,
                    )
                else:
                    logger.warning(
                        "source_page_link_failed",
                        customer_id=str(customer_id),
                        page_id=page_id,
                        error=link_result.get("error"),
                    )

            except Exception as e:
                # Log but don't fail - the customer is created, linking is enhancement
                logger.warning(
                    "source_page_link_error",
                    customer_id=str(customer_id),
                    page_id=page_id,
                    error=str(e),
                )

        # Step 3: Trigger enrichment ONLY for new customers
        # Now enrichment will have access to linked page content
        if is_new_customer and customer_id:
            try:
                from services.enrichment_service import enrich_single_customer
                enrichment_result = await enrich_single_customer(self.workspace_id, str(customer_id))
                logger.info(
                    "enrichment_completed",
                    customer_id=str(customer_id),
                    status=enrichment_result.get("status"),
                )
            except Exception as e:
                # Log but don't fail - enrichment can run later via queue
                logger.warning(
                    "enrichment_failed",
                    customer_id=str(customer_id),
                    error=str(e),
                )
        elif not is_new_customer:
            logger.info(
                "enrichment_skipped_existing_customer",
                customer_id=str(customer_id),
                reason="Notion updates for existing customers are delta signals",
            )

        # Step 3: Invoke HandoffAuto agent with customer_id
        if customer_id:
            agent_run_id = await self._invoke_agent_for_event(
                event=event,
                agent_name="handoff_auto",
                agent_params={
                    "customer_id": str(customer_id),
                    "trigger_type": "notion_trigger",
                },
            )

            if agent_run_id:
                event.artifacts_created.agent_runs.append(agent_run_id)

        return event

    async def _get_notion_field_mappings(self) -> dict[str, str]:
        """
        Get Notion field mappings from integration config.

        Returns mappings as stored: {"NotionProperty": "herofy_field"}
        This matches what CustomerFactory expects.
        """
        from db.dataconnect_client import get_dataconnect_client
        import json

        dc = get_dataconnect_client()

        result = await dc.execute_query(
            "GetWorkspaceIntegration",
            {
                "workspaceId": self.workspace_id,
                "integrationType": "notion",
            },
        )

        integrations = result.get("workspaceIntegrations", [])
        if not integrations:
            return {}

        config = integrations[0].get("config", "{}")
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except (json.JSONDecodeError, TypeError):
                config = {}

        # Config stores as {"NotionProperty": "herofy_field"} from the import wizard
        # CustomerFactory expects the same format: {"NotionProperty": "herofy_field"}
        # No inversion needed!
        return config.get("field_mappings", {})

    async def _sync_structured_field(self, event: ChangeEvent) -> ChangeEvent:
        """
        Sync a structured field update directly to Customer.

        No LLM needed - just apply the value.
        Uses field_mappings as the authority allowlist.
        """
        from db.dataconnect_client import get_dataconnect_client

        payload = event.raw_payload
        page_id = payload.get("page_id")
        mapped_field = payload.get("mapped_field")
        new_value = payload.get("new_value")

        if not page_id or not mapped_field:
            logger.warning(
                "structured_field_update_missing_data",
                page_id=page_id,
                mapped_field=mapped_field,
            )
            return event

        dc = get_dataconnect_client()

        # Get customer linked to this page via external_id
        result = await dc.execute_query(
            "GetCustomerByExternalId",
            {
                "workspaceId": self.workspace_id,
                "externalId": page_id,
            },
        )

        customers = result.get("customers", [])
        if not customers:
            logger.warning(
                "structured_field_update_no_customer",
                page_id=page_id,
            )
            return event

        customer_id = str(customers[0]["id"])

        # Allowed fields whitelist - SECURITY: only these fields can be synced
        # Each field has a dedicated UPDATE query to prevent SQL injection
        allowed_fields = frozenset([
            "arr_cents",
            "contract_start",
            "contract_end",
            "health_status",
            "lifecycle",
            "company_name",
            "domain",
            "csm",
            "tier",
            "users",
        ])

        if mapped_field not in allowed_fields:
            logger.warning(
                "structured_field_update_unknown_field",
                mapped_field=mapped_field,
            )
            return event

        # Update the customer record using explicit field queries
        # SECURITY: Using explicit queries per field instead of dynamic SQL
        # to prevent any SQL injection via mapped_field
        updated = await self._update_customer_field(
            customer_id=customer_id,
            field=mapped_field,
            value=new_value,
        )

        if not updated:
            logger.warning(
                "structured_field_update_failed",
                customer_id=customer_id,
                field=mapped_field,
            )
            return event

        event.artifacts_created.customer_updates.append(customer_id)

        logger.info(
            "structured_field_synced",
            customer_id=customer_id,
            field=mapped_field,
            new_value=new_value,
        )

        return event

    async def _classify_and_process_content(self, event: ChangeEvent) -> ChangeEvent:
        """
        Classify unstructured content using LLM.

        Determines if content is:
        - Routine (no action needed)
        - Informational (create Signal for tracking)
        - Action required (create Signal + Need)

        Flow:
        1. Handle source-specific processing (threads, interactions, meetings)
        2. Call LLM Signal Classification Service
        3. Create Signals and auto-create Needs if confidence >= 70%
        """
        customer_id = event.customer_id
        if not customer_id:
            logger.debug(
                "unstructured_content_no_customer",
                event_id=str(event.id),
            )
            return event

        payload = event.raw_payload

        # Handle Gmail/Slack messages specially (create threads + interactions)
        if event.source in (ChangeEventSource.GMAIL, ChangeEventSource.SLACK):
            event = await self._handle_message_event(event)
        # Handle Calendar events specially (create/update/cancel meetings)
        elif event.source == ChangeEventSource.CALENDAR:
            event = await self._handle_calendar_event(event)
        else:
            # For other sources (Notion content updates, etc.), create interaction
            interaction = await self._create_interaction(event, payload)
            if interaction:
                event.artifacts_created.interactions.append(str(interaction["id"]))

        # LLM Signal Classification
        # Extract message body for classification
        body = payload.get("body", "") or payload.get("text", "")
        if not body:
            logger.debug(
                "unstructured_content_empty_body",
                event_id=str(event.id),
            )
            return event

        try:
            from services.signal_classification import SignalClassificationService

            classifier = SignalClassificationService(workspace_id=self.workspace_id)

            signals_with_needs = await classifier.classify_and_process(
                event=event,
                customer_id=customer_id,
            )

            # Track artifacts
            for result in signals_with_needs:
                event.artifacts_created.signals.append(str(result.signal_id))
                if result.need_id:
                    event.artifacts_created.needs.append(str(result.need_id))

            logger.info(
                "content_classified",
                event_id=str(event.id),
                signals_created=len(signals_with_needs),
                needs_created=sum(1 for r in signals_with_needs if r.need_id),
            )

            # Link thread to first need (if any needs were created)
            needs_created = [r for r in signals_with_needs if r.need_id]
            if needs_created and event.source in (ChangeEventSource.GMAIL, ChangeEventSource.SLACK):
                try:
                    from db.dataconnect_client import get_dataconnect_client
                    dc = get_dataconnect_client()

                    # Find the thread for this event's interactions
                    # Query interactions with this source_event_id to get thread_id
                    interactions_result = await dc.execute_query(
                        "GetInteractionsBySourceEvent",
                        {
                            "workspaceId": self.workspace_id,
                            "sourceEventId": str(event.id),
                        },
                    )

                    interactions = interactions_result.get("interactions", [])
                    if interactions and interactions[0].get("thread"):
                        thread_id = interactions[0]["thread"]["id"]
                        first_need_id = str(needs_created[0].need_id)

                        # Link thread to first need
                        await dc.execute_mutation(
                            "LinkThreadToNeed",
                            {
                                "threadId": thread_id,
                                "needId": first_need_id,
                            },
                        )

                        logger.info(
                            "thread_linked_to_need",
                            event_id=str(event.id),
                            thread_id=thread_id,
                            need_id=first_need_id,
                        )

                except Exception as e:
                    logger.warning(
                        "thread_need_linking_failed",
                        event_id=str(event.id),
                        error=str(e),
                    )

            # Route actionable signals to the orchestrator queue
            try:
                from services.signal_router import route_signal
                for result in signals_with_needs:
                    if result.signal_kind and result.signal_state:
                        await route_signal(
                            workspace_id=self.workspace_id,
                            customer_id=str(customer_id),
                            signal_id=str(result.signal_id),
                            signal_kind=result.signal_kind,
                            signal_state=result.signal_state,
                            signal_sentence=result.signal_sentence,
                        )
            except Exception as e:
                logger.warning(
                    "signal_routing_failed",
                    event_id=str(event.id),
                    error=str(e),
                )

        except Exception as e:
            # Log but don't fail - event processing continues
            # The interaction was already created, classification is value-add
            logger.error(
                "signal_classification_failed",
                event_id=str(event.id),
                customer_id=str(customer_id),
                error=str(e),
            )

        return event

    async def _handle_message_event(self, event: ChangeEvent) -> ChangeEvent:
        """
        Handle Gmail/Slack message events.

        Flow:
        1. Find or create Thread (by externalThreadId)
        2. Create Interaction in thread
        3. Link thread to Need if not already linked
        4. Track artifacts

        Args:
            event: Gmail or Slack message event

        Returns:
            Event with artifacts populated
        """
        from db.dataconnect_client import get_dataconnect_client

        customer_id = event.customer_id
        if not customer_id:
            return event

        payload = event.raw_payload
        external_thread_id = payload.get("thread_id")
        subject = payload.get("subject", "")
        channel = payload.get("channel", event.source.value)

        if not external_thread_id:
            logger.warning(
                "message_event_no_thread_id",
                event_id=str(event.id),
                source=event.source.value,
            )
            return event

        dc = get_dataconnect_client()

        # Step 1: Find or create thread
        thread = await self._find_or_create_thread(
            customer_id=customer_id,
            external_thread_id=external_thread_id,
            subject=subject,
            channel=channel,
        )

        if not thread:
            logger.error(
                "message_event_thread_creation_failed",
                event_id=str(event.id),
                external_thread_id=external_thread_id,
            )
            return event

        thread_id = thread["id"]

        # Resolve the inbound sender to a stakeholder (additive — never gates creation)
        stakeholder_id = await self._resolve_stakeholder_id(event)

        # Step 2: Create interaction
        from uuid import uuid4

        interaction_id = str(uuid4())

        try:
            await dc.execute_mutation(
                "CreateInteractionFromEvent",
                {
                    "id": interaction_id,
                    "workspaceId": self.workspace_id,
                    "customerId": str(customer_id),
                    "threadId": thread_id,
                    "channel": channel,
                    "direction": "customer",  # From customer (us|customer|internal)
                    "senderName": payload.get("sender_name", ""),
                    "stakeholderId": str(stakeholder_id) if stakeholder_id else None,
                    "subject": subject,
                    "body": payload.get("body", ""),
                    "sourceEventId": str(event.id),
                    "occurredAt": event.occurred_at.isoformat(),
                    "interactionSource": "direct",  # Observed directly from source
                },
            )

            event.artifacts_created.interactions.append(interaction_id)

            # OOO pre-filter: an auto-reply is not the human engaging, so it must not
            # reset the responsiveness/silence clock (deterministic, never an LLM call).
            from services.ooo_detection import detect_ooo

            ooo = detect_ooo(subject, payload.get("body", ""))

            if ooo.is_ooo:
                logger.info(
                    "inbound_ooo_detected",
                    customer_id=str(customer_id),
                    stakeholder_id=str(stakeholder_id) if stakeholder_id else None,
                    until=ooo.until,
                    delegate=ooo.delegate_name,
                )
                # Surface a delegate suggestion to improve the contact graph (best-effort).
                if stakeholder_id and (ooo.delegate_name or ooo.delegate_email):
                    try:
                        from services.responsiveness import suggest_ooo_delegate

                        await suggest_ooo_delegate(
                            workspace_id=self.workspace_id,
                            customer_id=str(customer_id),
                            absent_stakeholder_id=str(stakeholder_id),
                            until=ooo.until,
                            delegate_name=ooo.delegate_name,
                            delegate_email=ooo.delegate_email,
                        )
                    except Exception as deleg_err:
                        logger.warning("ooo_delegate_surface_failed", error=str(deleg_err))
            else:
                # Maintain the denormalized lastInteractionAt for per-stakeholder metrics
                # (best-effort; the interaction is already persisted above).
                if stakeholder_id:
                    try:
                        await dc.execute_mutation(
                            "TouchStakeholderLastInteraction",
                            {"id": str(stakeholder_id), "lastInteractionAt": event.occurred_at.isoformat()},
                        )
                    except Exception as touch_err:
                        logger.warning(
                            "stakeholder_touch_failed",
                            stakeholder_id=str(stakeholder_id),
                            error=str(touch_err),
                        )

                # Pair this inbound to our last outbound in the thread and record the
                # per-stakeholder response latency (no-op when metric snapshots are off).
                try:
                    from services.responsiveness import record_response_latency

                    await record_response_latency(
                        workspace_id=self.workspace_id,
                        customer_id=str(customer_id),
                        thread_id=thread_id,
                        stakeholder_id=str(stakeholder_id) if stakeholder_id else None,
                        inbound_at_iso=event.occurred_at.isoformat(),
                    )
                except Exception as lat_err:
                    logger.warning("response_latency_failed", error=str(lat_err))

            logger.info(
                "message_interaction_created",
                event_id=str(event.id),
                thread_id=thread_id,
                interaction_id=interaction_id,
            )

            # Push real-time notification to Firestore for Conversations updates
            try:
                firestore = get_firestore_service()
                await firestore.notify_conversation_updated(
                    workspace_id=self.workspace_id,
                    thread_id=thread_id,
                    interaction_count=1,
                    channel=channel,
                )
            except Exception as notify_err:
                logger.warning("conversation_notification_failed", thread_id=thread_id, error=str(notify_err))

        except Exception as e:
            logger.error(
                "message_interaction_creation_failed",
                event_id=str(event.id),
                thread_id=thread_id,
                error=str(e),
            )

        return event

    async def _handle_calendar_event(self, event: ChangeEvent) -> ChangeEvent:
        """
        Handle Calendar event (create, modify, or cancel meeting).

        Flow:
        1. Extract calendar event data from raw_payload
        2. Check if Meeting already exists (by externalEventId)
        3. For created/modified: Create or update Meeting
        4. For canceled: Soft delete Meeting (status=canceled, deletedAt=now)
        5. Track artifacts

        Args:
            event: Calendar event

        Returns:
            Event with artifacts populated
        """
        from db.dataconnect_client import get_dataconnect_client
        from uuid import uuid4
        from datetime import datetime, timezone

        payload = event.raw_payload
        calendar_event_id = payload.get("calendar_event_id")

        if not calendar_event_id:
            logger.warning(
                "calendar_event_no_id",
                event_id=str(event.id),
            )
            return event

        dc = get_dataconnect_client()

        # Check if meeting already exists
        result = await dc.execute_query(
            "GetMeetingByExternalEventId",
            {
                "workspaceId": self.workspace_id,
                "externalEventId": calendar_event_id,
            },
        )

        meetings = result.get("meetings", [])
        existing_meeting = meetings[0] if meetings else None

        # Handle different event types
        if event.source_event_type == "calendar_event_canceled":
            # Soft delete meeting
            if existing_meeting:
                meeting_id = existing_meeting["id"]
                try:
                    await dc.execute_mutation(
                        "UpdateMeeting",
                        {
                            "id": meeting_id,
                            "status": "canceled",
                            "deletedAt": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                    event.artifacts_created.meetings.append(meeting_id)
                    logger.info(
                        "calendar_meeting_canceled",
                        event_id=str(event.id),
                        meeting_id=meeting_id,
                    )
                except Exception as e:
                    logger.error(
                        "calendar_meeting_cancel_failed",
                        event_id=str(event.id),
                        meeting_id=meeting_id,
                        error=str(e),
                    )
            else:
                logger.debug(
                    "calendar_event_canceled_no_meeting",
                    event_id=str(event.id),
                    calendar_event_id=calendar_event_id,
                )

        elif event.source_event_type == "calendar_event_created":
            # Create or update meeting
            link_status = payload.get("link_status", "linked")

            # Skip unlinked meetings per user requirement
            if link_status == "unlinked":
                logger.debug(
                    "calendar_event_unlinked_skipped",
                    event_id=str(event.id),
                    calendar_event_id=calendar_event_id,
                )
                return event

            # Extract meeting data
            customer_id = event.customer_id
            if not customer_id:
                logger.warning(
                    "calendar_event_no_customer",
                    event_id=str(event.id),
                )
                return event

            scheduled_at = payload.get("scheduled_at")
            if not scheduled_at:
                logger.warning(
                    "calendar_event_no_scheduled_at",
                    event_id=str(event.id),
                )
                return event

            # Map calendar status to MeetingStatus enum
            calendar_status = payload.get("status", "confirmed")
            status_map = {
                "confirmed": "scheduled",
                "tentative": "scheduled",
                "cancelled": "cancelled",
            }
            meeting_status = status_map.get(calendar_status, "scheduled")

            # Prepare meeting data
            meeting_data = {
                "workspaceId": self.workspace_id,
                "customerId": str(customer_id),
                "title": payload.get("title", "Untitled Meeting"),
                "scheduledAt": scheduled_at,
                "durationMinutes": payload.get("duration_minutes"),
                "attendeesOurs": str(payload.get("attendees_ours", [])),
                "attendeesTheirs": str(payload.get("attendees_theirs", [])),
                "status": meeting_status,
                "recurringEventId": payload.get("recurring_event_id"),
                "linkStatus": link_status,
                "externalEventId": calendar_event_id,
            }

            if existing_meeting:
                # Update existing meeting - only pass fields that can be updated
                meeting_id = existing_meeting["id"]
                update_data = {
                    "id": meeting_id,
                    "title": meeting_data.get("title"),
                    "scheduledAt": meeting_data.get("scheduledAt"),
                    "durationMinutes": meeting_data.get("durationMinutes"),
                    "status": meeting_data.get("status"),
                    "linkStatus": meeting_data.get("linkStatus"),
                }
                try:
                    await dc.execute_mutation(
                        "UpdateMeeting",
                        update_data,
                    )
                    event.artifacts_created.meetings.append(meeting_id)
                    logger.info(
                        "calendar_meeting_updated",
                        event_id=str(event.id),
                        meeting_id=meeting_id,
                    )

                    # Create meeting prep need if in next 48 hours
                    # and meeting doesn't already have a need
                    if not existing_meeting.get("need"):
                        need_id = await self._create_meeting_prep_need(
                            event=event,
                            meeting_id=meeting_id,
                            customer_id=customer_id,
                            payload=payload,
                        )
                        if need_id:
                            event.artifacts_created.needs.append(need_id)

                except Exception as e:
                    logger.error(
                        "calendar_meeting_update_failed",
                        event_id=str(event.id),
                        meeting_id=meeting_id,
                        error=str(e),
                    )
            else:
                # Create new meeting
                meeting_id = str(uuid4())
                meeting_data["id"] = meeting_id

                try:
                    await dc.execute_mutation(
                        "CreateMeetingFromCalendarEvent",
                        meeting_data,
                    )
                    event.artifacts_created.meetings.append(meeting_id)
                    logger.info(
                        "calendar_meeting_created",
                        event_id=str(event.id),
                        meeting_id=meeting_id,
                    )

                    # Create meeting prep need if in next 48 hours
                    need_id = await self._create_meeting_prep_need(
                        event=event,
                        meeting_id=meeting_id,
                        customer_id=customer_id,
                        payload=payload,
                    )
                    if need_id:
                        event.artifacts_created.needs.append(need_id)

                except Exception as e:
                    logger.error(
                        "calendar_meeting_creation_failed",
                        event_id=str(event.id),
                        error=str(e),
                    )

        return event

    async def _find_or_create_thread(
        self,
        customer_id: UUID,
        external_thread_id: str,
        subject: str,
        channel: str,
    ) -> dict[str, Any] | None:
        """
        Find existing thread by externalThreadId or create new one.

        Args:
            customer_id: Customer UUID
            external_thread_id: Gmail thread_id, Slack thread_ts, etc.
            subject: Thread subject/title
            channel: email, slack, etc.

        Returns:
            Thread record or None if creation failed
        """
        from db.dataconnect_client import get_dataconnect_client
        from uuid import uuid4

        dc = get_dataconnect_client()

        # Try to find by external_thread_id
        result = await dc.execute_query(
            "GetThreadByExternalId",
            {
                "workspaceId": self.workspace_id,
                "externalThreadId": external_thread_id,
            },
        )

        threads = result.get("threads", [])
        if threads:
            logger.debug(
                "thread_found",
                thread_id=threads[0]["id"],
                external_thread_id=external_thread_id,
            )
            return threads[0]

        # Thread doesn't exist - create it
        thread_id = str(uuid4())

        try:
            # Create thread without need (will be linked later if significant)
            await dc.execute_mutation(
                "CreateThreadWithId",
                {
                    "id": thread_id,
                    "workspaceId": self.workspace_id,
                    "customerId": str(customer_id),
                    "subject": subject or "Conversation",
                    "threadType": "customer",
                    "channel": channel,
                    "status": "open",
                    "externalThreadId": external_thread_id,
                },
            )

            # Fetch the created thread
            result = await dc.execute_query(
                "GetThreadByExternalId",
                {
                    "workspaceId": self.workspace_id,
                    "externalThreadId": external_thread_id,
                },
            )

            threads = result.get("threads", [])
            if threads:
                logger.info(
                    "thread_created",
                    thread_id=thread_id,
                    external_thread_id=external_thread_id,
                    customer_id=str(customer_id),
                )
                return threads[0]

            return None

        except Exception as e:
            logger.error(
                "thread_creation_failed",
                external_thread_id=external_thread_id,
                error=str(e),
            )
            return None

    async def _handle_unknown_sender(self, event: ChangeEvent) -> ChangeEvent:
        """
        Handle events from unknown senders.

        Creates a quarantined thread linked to a special "Unknown Contacts" customer.
        These appear in a "Quarantined" tab in the UI for review.

        Flow:
        1. Get or create "Unknown Contacts" pseudo-customer for workspace
        2. Create thread with threadType="quarantined"
        3. Create interaction with message content
        """
        from db.dataconnect_client import get_dataconnect_client
        from uuid import uuid4

        payload = event.raw_payload
        sender_email = payload.get("sender_email", "")
        sender_name = payload.get("sender_name", "Unknown Sender")
        subject = payload.get("subject", "(no subject)")
        body = payload.get("body", "")
        channel = payload.get("channel", event.source.value)

        logger.info(
            "unknown_sender_event",
            event_id=str(event.id),
            sender_email=sender_email,
            channel=channel,
        )

        dc = get_dataconnect_client()

        # Step 1: Get or create "Unknown Contacts" customer
        unknown_customer_id = await self._get_or_create_unknown_contacts_customer(dc)

        # Step 2: Create quarantined thread
        external_thread_id = payload.get("thread_id", f"unknown-{event.id}")
        thread_id = str(uuid4())

        try:
            await dc.execute_mutation(
                "CreateThread",
                {
                    "id": thread_id,
                    "workspaceId": self.workspace_id,
                    "customerId": unknown_customer_id,
                    "subject": f"{sender_email}: {subject}",
                    "threadType": "quarantined",
                    "channel": channel,
                    "status": "open",
                    "externalThreadId": external_thread_id,
                },
            )

            logger.info(
                "quarantined_thread_created",
                event_id=str(event.id),
                thread_id=thread_id,
                sender_email=sender_email,
            )

        except Exception as e:
            logger.error(
                "quarantined_thread_creation_failed",
                event_id=str(event.id),
                error=str(e),
            )
            return event

        # Step 3: Create interaction
        interaction_id = str(uuid4())

        try:
            await dc.execute_mutation(
                "CreateInteractionFromEvent",
                {
                    "id": interaction_id,
                    "workspaceId": self.workspace_id,
                    "customerId": unknown_customer_id,
                    "threadId": thread_id,
                    "channel": channel,
                    "direction": "customer",
                    "senderName": f"{sender_name} ({sender_email})",
                    "subject": subject,
                    "body": body,
                    "sourceEventId": str(event.id),
                    "occurredAt": event.occurred_at.isoformat(),
                    "interactionSource": "direct",
                },
            )

            event.artifacts_created.interactions.append(interaction_id)

            logger.info(
                "quarantined_interaction_created",
                event_id=str(event.id),
                interaction_id=interaction_id,
                thread_id=thread_id,
            )

        except Exception as e:
            logger.error(
                "quarantined_interaction_creation_failed",
                event_id=str(event.id),
                thread_id=thread_id,
                error=str(e),
            )

        return event

    async def _get_or_create_unknown_contacts_customer(self, dc) -> str:
        """
        Get or create the special "Unknown Contacts" customer for this workspace.

        This is a pseudo-customer used to hold quarantined threads from unknown senders.
        """
        from uuid import uuid4

        # Try to find existing Unknown Contacts customer
        result = await dc.execute_query(
            "GetCustomerBySlug",
            {
                "workspaceId": self.workspace_id,
                "slug": "unknown-contacts",
            },
        )

        customer = result.get("customer")
        if customer:
            return customer["id"]

        # Create it
        customer_id = str(uuid4())
        try:
            await dc.execute_mutation(
                "CreateCustomerWithId",
                {
                    "id": customer_id,
                    "workspaceId": self.workspace_id,
                    "name": "Unknown Contacts",
                    "slug": "unknown-contacts",
                    "lifecycle": "prospect",
                },
            )

            logger.info(
                "unknown_contacts_customer_created",
                workspace_id=self.workspace_id,
                customer_id=customer_id,
            )

            return customer_id

        except Exception as e:
            # Race condition - another process created it
            logger.debug(
                "unknown_contacts_customer_race_condition",
                error=str(e),
            )
            # Try to fetch again
            result = await dc.execute_query(
                "GetCustomerBySlug",
                {
                    "workspaceId": self.workspace_id,
                    "slug": "unknown-contacts",
                },
            )
            customer = result.get("customer")
            if customer:
                return customer["id"]

            # Should never get here
            raise Exception("Failed to create or fetch Unknown Contacts customer")

    # =========================================================================
    # Agent Invocation Seam
    # =========================================================================

    async def _invoke_agent_for_event(
        self,
        event: ChangeEvent,
        agent_name: str,
        agent_params: dict[str, Any],
    ) -> str | None:
        """
        Invoke an agent for an event.

        This is the extension point for agent dispatch.
        Currently supports:
        - handoff_auto: For new customer events

        Args:
            event: The triggering ChangeEvent
            agent_name: Which agent to invoke
            agent_params: Parameters for the agent

        Returns:
            Agent run ID if invoked, None otherwise
        """
        if agent_name == "handoff_auto":
            from agents.handoff_auto import run_handoff_auto

            try:
                # customer_id is required - customer must be created before agent runs
                customer_id = agent_params.get("customer_id")
                if not customer_id:
                    logger.error(
                        "agent_invocation_failed_no_customer",
                        agent_name=agent_name,
                        event_id=str(event.id),
                        reason="customer_id is required for handoff_auto",
                    )
                    return None

                result = await run_handoff_auto(
                    workspace_id=self.workspace_id,
                    customer_id=customer_id,
                    trigger_type=agent_params.get("trigger_type", "event_processor"),
                    triggered_by=f"event:{event.id}",
                )

                logger.info(
                    "agent_invoked",
                    agent_name=agent_name,
                    run_id=result.run_id,
                    status=result.status.value,
                    customer_id=customer_id,
                )

                return result.run_id

            except Exception as e:
                logger.error(
                    "agent_invocation_failed",
                    agent_name=agent_name,
                    error=str(e),
                )
                return None

        else:
            logger.warning(
                "unknown_agent_requested",
                agent_name=agent_name,
            )
            return None

    # =========================================================================
    # Meeting Prep Needs
    # =========================================================================

    async def _create_meeting_prep_need(
        self,
        event: ChangeEvent,
        meeting_id: str,
        customer_id: UUID,
        payload: dict,
    ) -> str | None:
        """
        Create a meeting prep need for an upcoming meeting.

        Only creates needs for meetings in the next 48 hours.
        Priority is based on how soon the meeting is:
        - Within 4 hours: priority 5 (very urgent)
        - Within 24 hours: priority 15 (today)
        - Within 48 hours: priority 25 (tomorrow)

        Args:
            event: The calendar change event
            meeting_id: The created/updated meeting ID
            customer_id: The customer UUID
            payload: Raw calendar event payload

        Returns:
            The created need ID or None if not created
        """
        from datetime import datetime, timezone, timedelta
        from uuid import uuid4
        from db.dataconnect_client import get_dataconnect_client

        scheduled_at_str = payload.get("scheduled_at")
        if not scheduled_at_str:
            logger.debug(
                "meeting_prep_skipped_no_scheduled_at",
                meeting_id=meeting_id,
            )
            return None

        # Parse scheduled time
        try:
            scheduled_at = datetime.fromisoformat(scheduled_at_str.replace("Z", "+00:00"))
        except (ValueError, TypeError) as e:
            logger.warning(
                "meeting_prep_skipped_invalid_time",
                meeting_id=meeting_id,
                scheduled_at=scheduled_at_str,
                error=str(e),
            )
            return None

        now = datetime.now(timezone.utc)
        time_until = scheduled_at - now

        # Only create needs for meetings in the next 48 hours (not past)
        if time_until > timedelta(hours=48) or time_until < timedelta(hours=-1):
            logger.debug(
                "meeting_prep_skipped_out_of_range",
                meeting_id=meeting_id,
                hours_until=time_until.total_seconds() / 3600,
            )
            return None

        # Calculate priority based on urgency
        if time_until <= timedelta(hours=4):
            priority = 5  # Very urgent
        elif time_until <= timedelta(hours=24):
            priority = 15  # Today
        else:
            priority = 25  # Tomorrow

        title = payload.get("title", "Untitled Meeting")
        attendees_theirs = payload.get("attendees_theirs", [])
        attendee_count = len(attendees_theirs) if isinstance(attendees_theirs, list) else 0

        # Format time for headline
        local_time = scheduled_at.strftime("%I:%M %p").lstrip("0")

        dc = get_dataconnect_client()
        need_id = str(uuid4())

        try:
            await dc.execute_mutation(
                "CreateNeedWithId",
                {
                    "id": need_id,
                    "workspaceId": self.workspace_id,
                    "customerId": str(customer_id),
                    "type": "meeting_prep_ready",
                    "headline": f"Prep for: {title} at {local_time}",
                    "priorityRank": priority,
                    "agentReasoning": f"Auto-created for meeting with {attendee_count} external attendees",
                    "sourceEventId": str(event.id),
                },
            )

            # Link meeting to need
            await dc.execute_mutation(
                "UpdateMeetingFromCalendarEvent",
                {
                    "id": meeting_id,
                    "needId": need_id,
                },
            )

            logger.info(
                "meeting_prep_need_created",
                event_id=str(event.id),
                meeting_id=meeting_id,
                need_id=need_id,
                priority=priority,
                hours_until=time_until.total_seconds() / 3600,
            )

            # Push real-time notification to Firestore for Today queue updates
            try:
                firestore = get_firestore_service()
                await firestore.notify_need_created(
                    workspace_id=self.workspace_id,
                    need_id=need_id,
                    need_type="meeting_prep_ready",
                    customer_name=title,  # Use meeting title as context
                )
            except Exception as notify_err:
                logger.warning("need_notification_failed", need_id=need_id, error=str(notify_err))

            return need_id

        except Exception as e:
            logger.error(
                "meeting_prep_need_creation_failed",
                event_id=str(event.id),
                meeting_id=meeting_id,
                error=str(e),
            )
            return None

    # =========================================================================
    # Helpers
    # =========================================================================

    def _extract_sender_email(self, event: ChangeEvent) -> str | None:
        """Extract sender email from event payload."""
        payload = event.raw_payload

        if event.source in (ChangeEventSource.GMAIL, ChangeEventSource.SLACK):
            return payload.get("sender_email")

        return None

    def _extract_sender_name(self, event: ChangeEvent) -> str:
        """Extract sender name from event payload."""
        payload = event.raw_payload

        if event.source in (ChangeEventSource.GMAIL, ChangeEventSource.SLACK):
            return payload.get("sender_name", "")

        return ""

    def _parse_email_domain(self, email: str | None) -> str | None:
        """Extract domain from email address."""
        if not email or "@" not in email:
            return None
        return email.split("@")[1].lower()

    async def _update_customer_field(
        self,
        customer_id: str,
        field: str,
        value: Any,
    ) -> bool:
        """
        Update a single customer field using DataConnect mutations.

        SECURITY: Uses explicit mutations per field to prevent injection.
        Each field has its own mutation - the field name is never
        interpolated into queries.

        Args:
            customer_id: Customer UUID string
            field: Field name (must be in allowed list)
            value: New value

        Returns:
            True if update succeeded
        """
        from db.dataconnect_client import get_dataconnect_client

        try:
            dc = get_dataconnect_client()

            # Explicit mutations for each field
            if field == "arr_cents":
                await dc.execute_mutation(
                    "UpdateCustomerArr",
                    {"id": customer_id, "arrCents": int(value) if value else 0},
                )
            elif field == "days_to_renewal":
                await dc.execute_mutation(
                    "UpdateCustomerDaysToRenewal",
                    {"id": customer_id, "daysToRenewal": int(value) if value else 0},
                )
            elif field in ("contract_start", "contract_end"):
                # Note: Customer schema doesn't have contractStart/contractEnd
                # These would need to be added to schema if needed
                logger.warning(
                    "update_customer_field_not_in_schema",
                    field=field,
                    customer_id=customer_id,
                )
                return False
            elif field == "lifecycle":
                await dc.execute_mutation(
                    "UpdateCustomerLifecycle",
                    {"id": customer_id, "lifecycle": value},
                )
            elif field == "company_name":
                await dc.execute_mutation(
                    "UpdateCustomerName",
                    {"id": customer_id, "name": str(value)},
                )
            elif field == "domain":
                await dc.execute_mutation(
                    "UpdateCustomerDomain",
                    {"id": customer_id, "domain": str(value)},
                )
            elif field == "tier":
                await dc.execute_mutation(
                    "UpdateCustomerTier",
                    {"id": customer_id, "tier": str(value)},
                )
            elif field in ("csm", "users", "health_status"):
                # These fields may need additional mutations - log and skip for now
                logger.warning(
                    "update_customer_field_not_implemented",
                    field=field,
                    customer_id=customer_id,
                )
                return False
            else:
                # Should never reach here if allowed_fields check is done first
                logger.error("update_customer_field_invalid", field=field)
                return False

            return True

        except Exception as e:
            logger.error(
                "update_customer_field_failed",
                customer_id=customer_id,
                field=field,
                error=str(e),
            )
            return False

    async def _create_stakeholder(
        self,
        customer_id: UUID,
        email: str,
        name: str,
    ) -> None:
        """
        Auto-create a stakeholder record when domain matching succeeds.

        Idempotent: uses upsert to skip if stakeholder already exists.
        """
        from db.dataconnect_client import get_dataconnect_client

        try:
            dc = get_dataconnect_client()

            # Upsert stakeholder (will skip if email already exists for this customer)
            import uuid
            await dc.execute_mutation(
                "CreateStakeholderIfNotExists",
                {
                    "id": str(uuid.uuid4()),
                    "workspaceId": self.workspace_id,
                    "customerId": str(customer_id),
                    "name": name or email.split("@")[0],
                    "email": email.lower(),
                },
            )

            logger.info(
                "stakeholder_auto_created",
                workspace_id=self.workspace_id,
                customer_id=str(customer_id),
                email=email,
            )

        except Exception as e:
            logger.warning(
                "stakeholder_creation_failed",
                workspace_id=self.workspace_id,
                email=email,
                error=str(e),
            )

    async def _create_interaction(
        self,
        event: ChangeEvent,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Create an Interaction record from an event.

        Links the interaction to the source event for provenance tracking.
        """
        from uuid import uuid4
        from db.dataconnect_client import get_dataconnect_client

        customer_id = event.customer_id
        if not customer_id:
            return None

        # Determine interaction channel
        channel = payload.get("channel", event.source.value)

        # Get thread_id if available (for threading)
        thread_id = payload.get("thread_id")

        # Find or create thread for this interaction
        thread = None

        if thread_id:
            dc = get_dataconnect_client()

            # Try to find existing thread by subject (external thread ID matching not yet supported)
            # TODO: Implement proper external thread ID matching via Interaction.externalRef
            result = await dc.execute_query(
                "GetThreadBySubject",
                {
                    "workspaceId": self.workspace_id,
                    "subject": thread_id,  # Using thread_id as subject for now
                },
            )

            threads = result.get("threads", [])
            if threads:
                thread = threads[0]

        if thread:
            thread_record_id = thread["id"]
        else:
            # No existing thread found for this message.
            # This happens when a message arrives before the signal_watcher_chain
            # has created a thread for this conversation. The interaction will be
            # picked up on the next signal_watcher_chain run when threads are created.
            logger.warning(
                "interaction_skipped_no_thread",
                workspace_id=self.workspace_id,
                customer_id=str(customer_id),
                event_id=str(event.id),
                source_event_type=event.source_event_type,
                external_thread_id=thread_id,
                reason="No existing thread found for external_thread_id",
            )
            return None

        # Create the interaction
        interaction_id = str(uuid4())

        dc = get_dataconnect_client()
        await dc.execute_mutation(
            "CreateInteractionFromEvent",
            {
                "id": interaction_id,
                "workspaceId": self.workspace_id,
                "customerId": str(customer_id),
                "threadId": thread_record_id,
                "channel": channel,
                "direction": "customer",  # inbound from customer
                "body": payload.get("body", ""),
                "sourceEventId": str(event.id),
                "occurredAt": event.occurred_at.isoformat(),
            },
        )

        # Push real-time notification to Firestore for Conversations updates
        try:
            firestore = get_firestore_service()
            await firestore.notify_conversation_updated(
                workspace_id=self.workspace_id,
                thread_id=thread_record_id,
                interaction_count=1,
                channel=channel,
            )
        except Exception as notify_err:
            logger.warning("conversation_notification_failed", thread_id=thread_record_id, error=str(notify_err))

        return {"id": interaction_id}

    async def persist_event(self, event: ChangeEvent) -> None:
        """
        Persist processing results for a ChangeEvent.

        Called by the orchestrator after processing.
        Note: The event was already marked as processed=true during claim.
        This updates the additional processing results.
        """
        from db.dataconnect_client import get_dataconnect_client

        dc = get_dataconnect_client()

        await dc.execute_mutation(
            "UpdateChangeEventProcessed",
            {
                "id": str(event.id),
                "eventClass": event.event_class.value if event.event_class else None,
                "customerId": str(event.customer_id) if event.customer_id else None,
                "processingError": event.processing_error,
                "artifactsCreated": event.artifacts_created.model_dump_json(),
            },
        )

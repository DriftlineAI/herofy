"""
Notion Event Emitter

Polls Notion for changes and emits ChangeEvents.
Replaces direct HandoffAuto triggering - now SignalWatcher decides what to do.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4
import json
import hashlib

from core.events import (
    ChangeEvent,
    ChangeEventSource,
    NotionTriggerConfig,
    NotionIntegrationConfig,
    NotionNewRecordPayload,
    NotionFieldUpdatePayload,
    NotionContentUpdatePayload,
)
from core.errors import (
    IntegrationNotConfiguredError,
    IntegrationTokenExpiredError,
    IntegrationAuthError,
)
from core.logging import get_logger
from integrations.clients.notion_client import NotionClient
from services import get_integration_service

from .base import EventEmitterBase

logger = get_logger("NotionEmitter")


class NotionEventEmitter(EventEmitterBase):
    """
    Emits ChangeEvents from Notion polling.

    Handles three types of events:
    1. notion_new_record - New page matching trigger criteria
    2. notion_field_update - Mapped property changed on existing customer
    3. notion_content_update - Rich text field changed on existing customer

    The emitter does NOT decide what to do with events - it just emits them.
    SignalWatcher handles routing (HandoffAuto for new_customer, etc.)
    """

    def _get_source_type(self) -> ChangeEventSource:
        return ChangeEventSource.NOTION

    async def poll_and_emit(
        self,
        since: datetime | None = None,
    ) -> list[ChangeEvent]:
        """
        Poll Notion and emit ChangeEvents.

        Returns list of ChangeEvents (not yet persisted).

        Error handling follows the EventEmitterBase contract:
        - IntegrationNotConfiguredError → return []
        - IntegrationTokenExpiredError → mark reconnection, return []
        - IntegrationAuthError → mark reconnection, return []
        - Generic Exception → log and re-raise
        """
        try:
            config_dict = await self.get_integration_config()
            if not config_dict:
                self._log_source_skipped("not_configured")
                return []

            try:
                config = NotionIntegrationConfig(**config_dict)
            except Exception as e:
                logger.error(
                    "invalid_notion_config",
                    workspace_id=self.workspace_id,
                    error=str(e),
                )
                return []

            watermark = since or await self.get_watermark()

            events = []

            # Get pages changed since watermark
            pages = await self._fetch_changed_pages(config, watermark)

            for page in pages:
                page_id = page.get("id")
                if not page_id:
                    continue

                # Check if this page is new (not in processed_deals)
                is_new = await self._is_new_page(page_id)

                if is_new:
                    # Extract property values for trigger matching
                    raw_props = page.get("properties", {})
                    extracted_props = {
                        name: self._extract_property_value(val)
                        for name, val in raw_props.items()
                    }

                    # Check if page matches trigger criteria
                    if config.trigger_config.matches_trigger(extracted_props):
                        event = self._create_new_record_event(page, config)
                        events.append(event)

                        # Get company name for logging
                        # field_mappings is {NotionProperty: herofy_field}
                        # Find the Notion property that maps to "name"
                        company_name = "Unknown"
                        for notion_prop, herofy_field in config.field_mappings.items():
                            if herofy_field == "name":
                                company_name = extracted_props.get(notion_prop, "Unknown")
                                break

                        logger.info(
                            "new_record_event_created",
                            page_id=page_id,
                            company=company_name,
                        )
                else:
                    # Existing page - check for field/content changes
                    field_events = await self._detect_field_changes(page, config)
                    content_events = await self._detect_content_changes(page, config)
                    events.extend(field_events)
                    events.extend(content_events)

            logger.info(
                "notion_poll_complete",
                workspace_id=self.workspace_id,
                pages_checked=len(pages),
                events_emitted=len(events),
            )

            return events

        except IntegrationNotConfiguredError:
            self._log_source_skipped("not_configured")
            return []

        except IntegrationTokenExpiredError:
            self._log_source_skipped("token_expired")
            await self._mark_needs_reconnection("Token expired")
            return []

        except IntegrationAuthError as e:
            self._log_source_skipped("auth_failed", str(e))
            await self._mark_needs_reconnection("Auth failed")
            return []

        except Exception as e:
            self._log_poll_failed(str(e))
            raise

    async def _fetch_changed_pages(
        self,
        config: NotionIntegrationConfig,
        since: datetime | None,
    ) -> list[dict[str, Any]]:
        """
        Fetch pages from the configured database.

        Uses NotionClient to query the database directly without hardcoded filters.
        If watermark is provided, filters by last_edited_time.
        """
        try:
            # Create NotionClient with integration service
            integration_service = get_integration_service(self.workspace_id)
            notion_client = NotionClient(integration_service)

            # Build filter if we have a watermark
            filter_obj = None
            if since:
                filter_obj = {
                    "timestamp": "last_edited_time",
                    "last_edited_time": {
                        "after": since.isoformat(),
                    },
                }

            # Fetch all pages with pagination
            all_pages = []
            cursor = None

            while True:
                result = await notion_client.query_database(
                    database_id=config.database_id,
                    filter=filter_obj,
                    page_size=100,
                    start_cursor=cursor,
                )

                all_pages.extend(result.get("results", []))

                if not result.get("has_more"):
                    break
                cursor = result.get("next_cursor")

            await notion_client.cleanup()

            logger.info(
                "notion_pages_fetched",
                workspace_id=self.workspace_id,
                database_id=config.database_id,
                count=len(all_pages),
                since=since.isoformat() if since else None,
            )

            return all_pages

        except Exception as e:
            logger.error(
                "notion_fetch_failed",
                workspace_id=self.workspace_id,
                database_id=config.database_id,
                error=str(e),
            )
            return []

    async def _is_new_page(self, page_id: str) -> bool:
        """
        Check if page has been processed before.

        Checks if a customer with this external_id already exists.
        This is the authoritative check for dedup.
        """
        from db.dataconnect_client import get_dataconnect_client
        dc = get_dataconnect_client()

        # Query for customer with this external ID
        result = await dc.execute_query(
            "GetCustomerByExternalId",
            {"workspaceId": self.workspace_id, "externalId": page_id},
        )

        customers = result.get("customers", [])
        return len(customers) == 0  # True if no customer exists (page is new)

    def _create_new_record_event(
        self,
        page: dict[str, Any],
        config: NotionIntegrationConfig,
    ) -> ChangeEvent:
        """Create ChangeEvent for new Notion record matching trigger."""
        page_id = page.get("id", "")

        # Get properties from raw Notion API format
        raw_props = page.get("properties", {})

        # Extract company name from the mapped "name" field
        # field_mappings is {NotionProperty: herofy_field}
        # Find the Notion property that maps to "name"
        company_name = "Unknown"
        for notion_prop, herofy_field in config.field_mappings.items():
            if herofy_field == "name" and notion_prop in raw_props:
                company_name = self._extract_property_value(raw_props[notion_prop]) or "Unknown"
                break

        # Collect all properties as extracted values
        all_properties = {}
        for prop_name, prop_value in raw_props.items():
            all_properties[prop_name] = self._extract_property_value(prop_value)

        # Collect rich text content for each configured field
        rich_text_content = {}
        for field in config.rich_text_fields:
            if field in raw_props:
                rich_text_content[field] = self._extract_property_value(raw_props[field])

        # Compute fingerprint (include created_time to ensure uniqueness for new records)
        created_time = page.get("created_time", "")
        fingerprint = ChangeEvent.compute_fingerprint(
            "notion",
            page_id,
            f"new_record_{created_time}",
        )

        # Parse occurred_at from page created_time
        occurred_at = self._parse_timestamp(page.get("created_time"))

        payload = NotionNewRecordPayload(
            page_id=page_id,
            company_name=company_name,
            properties=all_properties,
            rich_text_content=rich_text_content,
        )

        return ChangeEvent(
            id=uuid4(),
            workspace_id=UUID(self.workspace_id),
            source=ChangeEventSource.NOTION,
            source_event_type="notion_new_record",
            source_record_id=page_id,
            fingerprint=fingerprint,
            customer_id=None,  # Will be created by HandoffAuto
            raw_payload=payload.model_dump(),
            occurred_at=occurred_at,
        )

    async def _detect_field_changes(
        self,
        page: dict[str, Any],
        config: NotionIntegrationConfig,
    ) -> list[ChangeEvent]:
        """
        Detect changes to mapped Notion properties.

        Compares current property values against stored values on Customer.
        Only emits events for fields that actually changed.

        Authority rule: field_mappings IS the allowlist.
        Only fields in the mapping can be synced.
        """
        events = []
        page_id = page.get("id", "")

        if not config.field_mappings:
            return events

        # Get customer linked to this page
        customer = await self._get_customer_for_page(page_id)
        if not customer:
            return events

        raw_props = page.get("properties", {})

        # Check each mapped field for changes
        for notion_property, herofy_field in config.field_mappings.items():
            if notion_property not in raw_props:
                continue

            new_value = self._extract_property_value(raw_props[notion_property])
            old_value = customer.get(herofy_field)

            # Skip if no change
            if self._values_equal(old_value, new_value):
                continue

            fingerprint = ChangeEvent.compute_fingerprint(
                "notion",
                page_id,
                f"field_update_{notion_property}_{hashlib.md5(str(new_value).encode()).hexdigest()[:8]}",
            )

            payload = NotionFieldUpdatePayload(
                page_id=page_id,
                property_name=notion_property,
                mapped_field=herofy_field,
                old_value=old_value,
                new_value=new_value,
            )

            event = ChangeEvent(
                id=uuid4(),
                workspace_id=UUID(self.workspace_id),
                source=ChangeEventSource.NOTION,
                source_event_type="notion_field_update",
                source_record_id=page_id,
                fingerprint=fingerprint,
                customer_id=customer.get("id"),
                raw_payload=payload.model_dump(),
                occurred_at=self._parse_timestamp(page.get("last_edited_time")),
            )
            events.append(event)

            logger.info(
                "field_change_detected",
                page_id=page_id,
                field=herofy_field,
                old_value=old_value,
                new_value=new_value,
            )

        return events

    async def _detect_content_changes(
        self,
        page: dict[str, Any],
        config: NotionIntegrationConfig,
    ) -> list[ChangeEvent]:
        """
        Detect changes to unstructured rich text fields.

        Per-field diffing: only emit events for fields that actually changed.
        Compares against Customer.rawContext JSON blob.
        """
        events = []
        page_id = page.get("id", "")

        if not config.rich_text_fields:
            return events

        # Get customer linked to this page
        customer = await self._get_customer_for_page(page_id)
        if not customer:
            return events

        # Get stored rawContext
        raw_context_str = customer.get("raw_context") or customer.get("rawContext") or "{}"
        try:
            old_context = json.loads(raw_context_str) if isinstance(raw_context_str, str) else raw_context_str
        except json.JSONDecodeError:
            old_context = {}

        raw_props = page.get("properties", {})

        # Check each rich text field for changes
        for field in config.rich_text_fields:
            new_content = None

            if field in raw_props:
                new_content = self._extract_property_value(raw_props[field])

            if new_content is None:
                continue

            old_content = old_context.get(field)

            # Skip if no change (normalize whitespace for comparison)
            if self._content_equal(old_content, new_content):
                continue

            fingerprint = ChangeEvent.compute_fingerprint(
                "notion",
                page_id,
                f"content_update_{field}_{hashlib.md5(str(new_content).encode()).hexdigest()[:8]}",
            )

            payload = NotionContentUpdatePayload(
                page_id=page_id,
                field_name=field,
                old_content=old_content,
                new_content=new_content,
            )

            event = ChangeEvent(
                id=uuid4(),
                workspace_id=UUID(self.workspace_id),
                source=ChangeEventSource.NOTION,
                source_event_type="notion_content_update",
                source_record_id=page_id,
                fingerprint=fingerprint,
                customer_id=customer.get("id"),
                raw_payload=payload.model_dump(),
                occurred_at=self._parse_timestamp(page.get("last_edited_time")),
            )
            events.append(event)

            logger.info(
                "content_change_detected",
                page_id=page_id,
                field=field,
                old_length=len(old_content) if old_content else 0,
                new_length=len(new_content) if new_content else 0,
            )

        return events

    async def _get_customer_for_page(self, page_id: str) -> dict[str, Any] | None:
        """Get customer record linked to a Notion page via external_id."""
        from db.dataconnect_client import get_dataconnect_client
        dc = get_dataconnect_client()

        result = await dc.execute_query(
            "GetCustomerByExternalId",
            {"workspaceId": self.workspace_id, "externalId": page_id},
        )

        customers = result.get("customers", [])
        return customers[0] if customers else None

    def _extract_property_value(self, prop: Any) -> Any:
        """Extract value from Notion property object."""
        if prop is None:
            return None

        # If it's already a simple value, return it
        if isinstance(prop, (str, int, float, bool)):
            return prop

        if not isinstance(prop, dict):
            return str(prop)

        prop_type = prop.get("type")

        if prop_type == "title":
            return "".join([t.get("plain_text", "") for t in prop.get("title", [])])
        elif prop_type == "rich_text":
            return "".join([t.get("plain_text", "") for t in prop.get("rich_text", [])])
        elif prop_type == "number":
            return prop.get("number")
        elif prop_type == "select":
            select = prop.get("select", {})
            return select.get("name") if select else None
        elif prop_type == "status":
            status = prop.get("status", {})
            return status.get("name") if status else None
        elif prop_type == "multi_select":
            return [s.get("name") for s in prop.get("multi_select", [])]
        elif prop_type == "date":
            date = prop.get("date", {})
            return date.get("start") if date else None
        elif prop_type == "checkbox":
            return prop.get("checkbox", False)
        elif prop_type == "url":
            return prop.get("url")
        elif prop_type == "email":
            return prop.get("email")
        elif prop_type == "phone_number":
            return prop.get("phone_number")

        # Fallback: return the raw value
        return prop

    def _values_equal(self, old: Any, new: Any) -> bool:
        """Compare two values for equality, handling type differences."""
        if old is None and new is None:
            return True
        if old is None or new is None:
            return False

        # Normalize to strings for comparison
        old_str = str(old).strip() if old else ""
        new_str = str(new).strip() if new else ""
        return old_str == new_str

    def _content_equal(self, old: str | None, new: str | None) -> bool:
        """Compare content strings, normalizing whitespace."""
        if old is None and new is None:
            return True
        if old is None or new is None:
            return False

        # Normalize whitespace
        old_normalized = " ".join(old.split())
        new_normalized = " ".join(new.split())
        return old_normalized == new_normalized

    def _parse_timestamp(self, value: Any) -> datetime:
        """Parse a timestamp value to datetime."""
        if value is None:
            return datetime.now(timezone.utc)

        if isinstance(value, datetime):
            return value

        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                pass

        return datetime.now(timezone.utc)

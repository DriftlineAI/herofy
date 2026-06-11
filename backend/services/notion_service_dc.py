"""
Notion Service (DataConnect Version)
Business logic for Notion integration - deal polling, watermarks, deduplication
"""

from datetime import datetime
from typing import Any
import json

from db.dataconnect_client import DataConnectClient
from core.logging import get_logger
from core.types import IntegrationType, NotionDeal, NotionConfig
from core.errors import IntegrationNotConfiguredError
from tools.notion_tool import read_notion_deal, list_closed_deals

logger = get_logger("NotionServiceDC")


# Agent state keys
WATERMARK_KEY = "notion_closed_deals_watermark"


class NotionServiceDC:
    """Service for Notion MCP operations with watermark management using DataConnect."""

    def __init__(self, dc: DataConnectClient, workspace_id: str):
        self.dc = dc
        self.workspace_id = workspace_id

    async def get_config(self) -> NotionConfig | None:
        """
        Get Notion configuration for the workspace.

        Returns:
            NotionConfig if configured, None otherwise
        """
        result = await self.dc.execute_query(
            "GetWorkspaceIntegration",
            {
                "workspaceId": self.workspace_id,
                "integrationType": IntegrationType.NOTION.value,
            },
        )

        integrations = result.get("workspaceIntegrations", [])
        if not integrations:
            return None

        integration = integrations[0]

        # Check if status is active
        if integration.get("status") != "active":
            return None

        config = integration.get("config", "{}")
        # Config is stored as JSON string in the database
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except (json.JSONDecodeError, TypeError):
                config = {}

        if not config.get("database_id"):
            return None

        return NotionConfig(
            database_id=config["database_id"],
            database_name=config.get("database_name"),
            field_mappings=config.get("field_mappings"),
        )

    async def get_watermark(self) -> datetime | None:
        """
        Get the last successful poll timestamp.

        Returns:
            Datetime of last poll, or None if never polled
        """
        result = await self.dc.execute_query(
            "GetAgentState",
            {
                "workspaceId": self.workspace_id,
                "key": WATERMARK_KEY,
            },
        )

        states = result.get("agentStates", [])
        if not states:
            return None

        state = states[0]
        value = state.get("value")

        if not value:
            return None

        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    async def update_watermark(self, timestamp: datetime) -> None:
        """
        Update the watermark to the given timestamp.

        Args:
            timestamp: New watermark value
        """
        await self.dc.execute_mutation(
            "UpsertAgentState",
            {
                "workspaceId": self.workspace_id,
                "key": WATERMARK_KEY,
                "value": timestamp.isoformat(),
            },
        )

        logger.info(
            "watermark_updated",
            workspace_id=self.workspace_id,
            watermark=timestamp.isoformat(),
        )

    async def poll_closed_deals(self) -> list[NotionDeal]:
        """
        Poll for newly closed deals since the last watermark.

        Returns:
            List of new deals to process

        Raises:
            IntegrationNotConfiguredError: If Notion not configured
        """
        config = await self.get_config()
        if not config:
            raise IntegrationNotConfiguredError(
                self.workspace_id, IntegrationType.NOTION.value
            )

        watermark = await self.get_watermark()

        logger.info(
            "polling_closed_deals",
            workspace_id=self.workspace_id,
            database_id=config.database_id,
            since=watermark.isoformat() if watermark else None,
        )

        # Call the tool function
        raw_deals = await list_closed_deals(
            workspace_id=self.workspace_id,
            since_timestamp=watermark.isoformat() if watermark else None,
        )

        # Filter out already processed deals
        new_deals = []
        for raw_deal in raw_deals:
            page_id = raw_deal.get("page_id")
            if not page_id:
                continue

            # Check if already processed
            if await self._is_deal_processed(page_id):
                logger.debug("deal_already_processed", page_id=page_id)
                continue

            # Convert to NotionDeal
            deal = NotionDeal(
                page_id=page_id,
                company_name=raw_deal.get("company_name", "Unknown"),
                arr_cents=raw_deal.get("arr_cents"),
                closed_at=_parse_datetime(raw_deal.get("closed_at")),
                timeline=raw_deal.get("timeline"),
                sales_commitments=raw_deal.get("sales_commitments", []),
                technical_context=raw_deal.get("technical_context", []),
                stakeholders=raw_deal.get("stakeholders", []),
                notes=raw_deal.get("notes"),
                raw_properties=raw_deal.get("properties"),
            )
            new_deals.append(deal)

        logger.info(
            "poll_complete",
            workspace_id=self.workspace_id,
            total_found=len(raw_deals),
            new_deals=len(new_deals),
        )

        return new_deals

    async def fetch_deal(self, notion_deal_id: str) -> NotionDeal | None:
        """
        Fetch a specific deal by Notion page ID.

        Args:
            notion_deal_id: Notion page ID

        Returns:
            NotionDeal if found, None otherwise
        """
        try:
            raw_deal = await read_notion_deal(notion_deal_id)

            if "error" in raw_deal:
                logger.error(
                    "fetch_deal_failed",
                    page_id=notion_deal_id,
                    error=raw_deal["error"],
                )
                return None

            return NotionDeal(
                page_id=notion_deal_id,
                company_name=raw_deal.get("company_name", "Unknown"),
                arr_cents=raw_deal.get("arr_cents"),
                closed_at=_parse_datetime(raw_deal.get("closed_at")),
                timeline=raw_deal.get("timeline"),
                sales_commitments=[
                    {"item": c.get("item", c), "details": c.get("details")}
                    for c in raw_deal.get("sales_commitments", [])
                ],
                technical_context=[
                    {"item": t.get("item", t), "details": t.get("details")}
                    for t in raw_deal.get("technical_context", [])
                ],
                stakeholders=raw_deal.get("stakeholders", []),
                notes=raw_deal.get("notes"),
            )

        except Exception as e:
            logger.error(
                "fetch_deal_error",
                page_id=notion_deal_id,
                error=str(e),
            )
            return None

    async def mark_deal_processed(
        self,
        notion_deal_id: str,
        agent_run_id: str | None = None,
        customer_id: str | None = None,
        brief_id: str | None = None,
        status: str = "processed",
        skip_reason: str | None = None,
    ) -> dict[str, Any]:
        """
        Mark a deal as processed to prevent reprocessing.

        Args:
            notion_deal_id: Notion page ID
            agent_run_id: The agent run that processed this deal
            customer_id: Created customer ID
            brief_id: Created handoff brief ID
            status: Processing status ('processed', 'skipped', 'failed')
            skip_reason: Why the deal was skipped

        Returns:
            Created processed_deal record
        """
        result = await self.dc.execute_mutation(
            "CreateProcessedDeal",
            {
                "workspaceId": self.workspace_id,
                "notionDealId": notion_deal_id,
                "agentRunId": agent_run_id,
                "customerId": customer_id,
                "briefId": brief_id,
                "status": status,
                "skipReason": skip_reason,
            },
        )

        record = result.get("processedDeal_insert", {})

        logger.info(
            "deal_marked_processed",
            notion_deal_id=notion_deal_id,
            status=status,
        )

        return record

    async def _is_deal_processed(self, notion_deal_id: str) -> bool:
        """
        Check if a deal has already been processed.

        Checks both:
        1. processed_deals table (poll-based processing)
        2. customers table with matching external_id (import-based processing)

        Args:
            notion_deal_id: Notion page ID

        Returns:
            True if already processed or customer exists
        """
        # Check processed_deals table
        result = await self.dc.execute_query(
            "CheckProcessedDeal",
            {
                "workspaceId": self.workspace_id,
                "notionDealId": notion_deal_id,
            },
        )

        deals = result.get("processedDeals", [])
        if len(deals) > 0:
            return True

        # Also check if customer already exists with this external_id
        # (handles records imported via UI, not poll)
        customer_result = await self.dc.execute_query(
            "GetCustomerByExternalId",
            {
                "workspaceId": self.workspace_id,
                "externalId": notion_deal_id,
            },
        )

        customers = customer_result.get("customers", [])
        return len(customers) > 0

    async def get_processed_deals(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Get list of processed deals.

        Args:
            limit: Max records to return
            offset: Pagination offset

        Returns:
            List of processed deal records
        """
        result = await self.dc.execute_query(
            "GetProcessedDeals",
            {
                "workspaceId": self.workspace_id,
                "limit": limit,
                "offset": offset,
            },
        )

        deals = result.get("processedDeals", [])

        # Transform nested data to match legacy format
        for deal in deals:
            # Extract customer name
            customer = deal.pop("customer", None)
            if customer:
                deal["customer_name"] = customer.get("name")

            # Extract agent run info
            agent_run = deal.pop("agentRun", None)
            if agent_run:
                deal["agent_run_id"] = agent_run.get("id")
                deal["agent_name"] = agent_run.get("agentName")

            # Extract brief info
            brief = deal.pop("brief", None)
            if brief:
                deal["brief_id"] = brief.get("id")

        return deals

    async def poll_and_sync(self) -> dict[str, Any]:
        """
        Poll Notion for new closed deals and trigger handoff workflows.

        This is the main entry point for the polling system.

        Returns:
            Summary of what was processed:
            - new_deals: Number of new deals found
            - triggered_agents: Number of handoff agents triggered
        """
        try:
            # Poll for new closed deals
            new_deals = await self.poll_closed_deals()

            if not new_deals:
                logger.info(
                    "poll_and_sync_no_new_deals",
                    workspace_id=self.workspace_id,
                )
                return {"new_deals": 0, "triggered_agents": 0}

            logger.info(
                "poll_and_sync_found_deals",
                workspace_id=self.workspace_id,
                count=len(new_deals),
            )

            # Trigger handoff agent for each new deal
            triggered_count = 0
            for deal in new_deals:
                try:
                    await self._trigger_handoff_agent(deal)
                    triggered_count += 1
                except Exception as e:
                    logger.error(
                        "handoff_trigger_failed",
                        workspace_id=self.workspace_id,
                        page_id=deal.page_id,
                        error=str(e),
                    )
                    # Continue processing other deals

            # Update watermark to latest deal's timestamp
            if new_deals:
                latest_timestamp = max(
                    d.closed_at for d in new_deals if d.closed_at
                ) or datetime.utcnow()
                await self.update_watermark(latest_timestamp)

            return {
                "new_deals": len(new_deals),
                "triggered_agents": triggered_count,
            }

        except IntegrationNotConfiguredError:
            logger.info(
                "poll_and_sync_skipped",
                workspace_id=self.workspace_id,
                reason="not_configured",
            )
            return {"new_deals": 0, "triggered_agents": 0}

    async def _trigger_handoff_agent(self, deal: NotionDeal) -> None:
        """
        Trigger the handoff agent for a new deal.

        Args:
            deal: The deal to process
        """
        # Mark deal as processed first (to prevent duplicate processing)
        await self.mark_deal_processed(
            notion_deal_id=deal.page_id,
            status="processing",
        )

        try:
            # Import agent trigger function
            # This triggers the handoff_auto agent which will:
            # 1. Create a customer record
            # 2. Create a handoff brief
            # 3. Generate an onboarding plan
            # 4. Create a plan_approval_required need

            # For now, we just log - the actual agent trigger will be
            # implemented based on the existing handoff_auto agent
            logger.info(
                "handoff_agent_triggered",
                workspace_id=self.workspace_id,
                page_id=deal.page_id,
                company_name=deal.company_name,
            )

            # TODO: Actually trigger the agent
            # from agents.handoff_auto.agent import trigger_handoff
            # await trigger_handoff(self.workspace_id, deal.page_id)

        except Exception as e:
            # Mark as failed
            # First, get the deal record ID to update it
            result = await self.dc.execute_query(
                "CheckProcessedDeal",
                {
                    "workspaceId": self.workspace_id,
                    "notionDealId": deal.page_id,
                },
            )

            deals = result.get("processedDeals", [])
            if deals:
                deal_id = deals[0].get("id")
                await self.dc.execute_mutation(
                    "UpdateProcessedDealStatus",
                    {
                        "id": deal_id,
                        "status": "failed",
                        "skipReason": str(e)[:500],
                    },
                )
            raise


def _parse_datetime(value: Any) -> datetime | None:
    """Parse a datetime value from various formats."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


# =============================================================================
# Page Linking Helpers (shared between manual linking and poll auto-linking)
# =============================================================================


def extract_body_text_from_blocks(blocks: dict) -> str:
    """
    Extract plain text from Notion page body blocks.

    This extracts text content that will be processed by the AI enrichment
    service to generate structured customer data.

    Args:
        blocks: Notion blocks response from get_block_children

    Returns:
        Combined plain text from blocks
    """
    results = blocks.get("results", [])
    texts: list[str] = []

    for block in results:
        block_type = block.get("type")

        if block_type == "paragraph":
            rich_text = block.get("paragraph", {}).get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in rich_text)
            if text:
                texts.append(text)

        elif block_type == "bulleted_list_item":
            rich_text = block.get("bulleted_list_item", {}).get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in rich_text)
            if text:
                texts.append(f"• {text}")

        elif block_type == "numbered_list_item":
            rich_text = block.get("numbered_list_item", {}).get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in rich_text)
            if text:
                texts.append(text)

        elif block_type in ("heading_1", "heading_2", "heading_3"):
            heading_data = block.get(block_type, {})
            rich_text = heading_data.get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in rich_text)
            if text:
                texts.append(f"\n{text}\n")

        elif block_type == "quote":
            rich_text = block.get("quote", {}).get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in rich_text)
            if text:
                texts.append(f"> {text}")

        elif block_type == "callout":
            rich_text = block.get("callout", {}).get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in rich_text)
            if text:
                texts.append(f"[Note] {text}")

        elif block_type == "toggle":
            rich_text = block.get("toggle", {}).get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in rich_text)
            if text:
                texts.append(f"▸ {text}")

        elif block_type == "to_do":
            rich_text = block.get("to_do", {}).get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in rich_text)
            checked = block.get("to_do", {}).get("checked", False)
            if text:
                prefix = "☑" if checked else "☐"
                texts.append(f"{prefix} {text}")

    return "\n".join(texts)


def extract_all_text_from_properties(props: dict, notion_client, mapped_props: set[str] | None = None) -> str:
    """
    Extract ALL text content from Notion properties for enrichment.

    Automatically pulls from any rich_text property that isn't already
    mapped to a structured field. This captures notes, descriptions,
    comments, and any other freeform text.

    Args:
        props: Notion properties dict
        notion_client: NotionClient instance for parsing
        mapped_props: Set of property names already mapped to structured fields (optional)

    Returns:
        Combined text from all text properties, with labels
    """
    if mapped_props is None:
        mapped_props = set()

    text_parts = []

    for prop_name, prop_data in props.items():
        # Skip properties that are explicitly mapped to structured fields
        if prop_name in mapped_props:
            continue

        prop_type = prop_data.get("type", "")

        # Extract from rich_text properties (Notes, Description, Comments, etc.)
        if prop_type == "rich_text":
            text = notion_client._get_text(prop_data)
            if text and text.strip():
                text_parts.append(f"**{prop_name}:**\n{text}")

        # Also extract from title (gives context on what this record is)
        elif prop_type == "title":
            text = notion_client._get_title(prop_data)
            if text and text.strip():
                text_parts.append(f"**{prop_name}:** {text}")

    return "\n\n".join(text_parts)


async def link_notion_page_to_customer(
    workspace_id: str,
    customer_id: str,
    page_id: str,
    page_title: str | None = None,
    page_type: str = "crm_record",
    trigger_enrichment: bool = True,
) -> dict[str, Any]:
    """
    Link a Notion page to a customer, fetching and storing its content.

    This is the shared service function used by:
    - Manual page linking (setup flow)
    - Auto-linking source page on poll (new customer flow)

    Args:
        workspace_id: Workspace UUID
        customer_id: Customer UUID to link to
        page_id: Notion page ID to fetch and link
        page_title: Optional title (will be fetched if not provided)
        page_type: Type of page (crm_record, handoff_doc, meeting_notes, etc.)
        trigger_enrichment: Whether to trigger re-enrichment after linking

    Returns:
        Dict with:
        - success: bool
        - linked_page: The linked page object (if successful)
        - content_length: Length of extracted content
        - error: Error message (if failed)
    """
    from db.dataconnect_client import get_dataconnect_client
    from services import get_integration_service
    from integrations.clients.notion_client import NotionClient

    dc = get_dataconnect_client()

    try:
        # Get current customer to read existing linked pages
        result = await dc.execute_query("GetCustomer", {"id": customer_id})
        customer = result.get("customer")

        if not customer:
            return {"success": False, "error": "Customer not found"}

        # Parse existing linked pages
        existing_json = customer.get("linkedPages")
        linked_pages: list[dict] = []
        if existing_json:
            try:
                linked_pages = json.loads(existing_json)
            except json.JSONDecodeError:
                linked_pages = []

        # Check if page already linked
        for page in linked_pages:
            if page.get("source") == "notion" and page.get("id") == page_id:
                logger.info(
                    "page_already_linked",
                    customer_id=customer_id,
                    page_id=page_id,
                )
                return {
                    "success": True,
                    "linked_page": page,
                    "already_linked": True,
                }

        # Fetch page content (properties + body blocks)
        page_content: str | None = None
        fetched_title = page_title

        try:
            integration_service = get_integration_service(workspace_id)
            notion_client = NotionClient(integration_service)

            content_parts = []

            # 1. Fetch page properties
            try:
                page = await notion_client.get_page(page_id)
                props = page.get("properties", {})

                # Get title from properties if not provided
                if not fetched_title:
                    for prop_name, prop_data in props.items():
                        if prop_data.get("type") == "title":
                            fetched_title = notion_client._get_title(prop_data)
                            break

                # Extract all text from properties
                property_text = extract_all_text_from_properties(props, notion_client)
                if property_text and property_text.strip():
                    content_parts.append(f"**Properties:**\n{property_text}")

            except Exception as e:
                logger.warning(
                    "notion_page_properties_fetch_failed",
                    page_id=page_id,
                    error=str(e),
                )

            # 2. Fetch page body blocks
            try:
                blocks = await notion_client.get_block_children(page_id)
                body_text = extract_body_text_from_blocks(blocks)
                if body_text and body_text.strip():
                    content_parts.append(f"**Page Content:**\n{body_text}")

            except Exception as e:
                logger.warning(
                    "notion_page_blocks_fetch_failed",
                    page_id=page_id,
                    error=str(e),
                )

            # Combine properties + body content
            page_content = "\n\n---\n\n".join(content_parts) if content_parts else None

            await notion_client.cleanup()

            logger.info(
                "notion_page_content_fetched",
                customer_id=customer_id,
                page_id=page_id,
                content_length=len(page_content) if page_content else 0,
            )

        except Exception as e:
            logger.warning(
                "notion_page_content_fetch_failed",
                customer_id=customer_id,
                page_id=page_id,
                error=str(e),
            )
            # Continue without content - we can still link the page

        # Build page URL
        clean_page_id = page_id.replace("-", "")
        page_url = f"https://notion.so/{clean_page_id}"

        # Add new linked page with content
        new_page = {
            "source": "notion",
            "id": page_id,
            "type": page_type,
            "url": page_url,
            "title": fetched_title or "Untitled",
            "content": page_content,
            "hasAccess": True,
        }
        linked_pages.append(new_page)

        # Save updated linked pages
        await dc.execute_mutation(
            "UpdateCustomerLinkedPages",
            {
                "id": customer_id,
                "linkedPages": json.dumps(linked_pages),
            },
        )

        logger.info(
            "page_linked_to_customer",
            customer_id=customer_id,
            page_id=page_id,
            page_type=page_type,
            has_content=page_content is not None,
            content_length=len(page_content) if page_content else 0,
        )

        # Trigger re-enrichment if we have new content to process
        if trigger_enrichment and page_content:
            try:
                await dc.execute_mutation(
                    "UpdateCustomerEnrichmentStatus",
                    {
                        "id": customer_id,
                        "enrichmentStatus": "pending",
                        "enrichmentAttempts": 0,
                        "enrichmentError": None,
                    },
                )
                logger.info(
                    "customer_marked_for_reenrichment",
                    customer_id=customer_id,
                    reason="linked_page_content",
                )
            except Exception as e:
                logger.warning(
                    "reenrichment_trigger_failed",
                    customer_id=customer_id,
                    error=str(e),
                )

        return {
            "success": True,
            "linked_page": new_page,
            "content_length": len(page_content) if page_content else 0,
        }

    except Exception as e:
        logger.error(
            "link_page_error",
            customer_id=customer_id,
            page_id=page_id,
            error=str(e),
        )
        return {"success": False, "error": str(e)}

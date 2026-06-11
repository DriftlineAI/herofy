"""
Notion Service
Business logic for Notion integration - deal polling, watermarks, deduplication
"""

from datetime import datetime
from typing import Any

from db.client import DatabaseClient
from core.logging import get_logger
from core.types import IntegrationType, NotionDeal, NotionConfig
from core.errors import IntegrationNotConfiguredError
from tools.notion_tool import read_notion_deal, list_closed_deals

logger = get_logger("NotionService")


# Agent state keys
WATERMARK_KEY = "notion_closed_deals_watermark"


class NotionService:
    """Service for Notion MCP operations with watermark management."""

    def __init__(self, db: DatabaseClient, workspace_id: str):
        self.db = db
        self.workspace_id = workspace_id

    async def get_config(self) -> NotionConfig | None:
        """
        Get Notion configuration for the workspace.

        Returns:
            NotionConfig if configured, None otherwise
        """
        import json

        integration = await self.db.query_one(
            """
            SELECT * FROM workspace_integrations
            WHERE workspace_id = $1 AND integration_type = $2 AND status = 'active'
            """,
            [self.workspace_id, IntegrationType.NOTION.value],
        )

        if not integration:
            return None

        config = integration.get("config", {})
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
        row = await self.db.query_one(
            """
            SELECT value FROM agent_state
            WHERE workspace_id = $1 AND key = $2
            """,
            [self.workspace_id, WATERMARK_KEY],
        )

        if not row or not row.get("value"):
            return None

        try:
            return datetime.fromisoformat(row["value"].replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    async def update_watermark(self, timestamp: datetime) -> None:
        """
        Update the watermark to the given timestamp.

        Args:
            timestamp: New watermark value
        """
        # Upsert the watermark
        await self.db.execute(
            """
            INSERT INTO agent_state (workspace_id, key, value, updated_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (workspace_id, key) DO UPDATE
            SET value = $3, updated_at = NOW()
            """,
            [self.workspace_id, WATERMARK_KEY, timestamp.isoformat()],
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
        record = await self.db.insert(
            "processed_deals",
            {
                "workspace_id": self.workspace_id,
                "notion_deal_id": notion_deal_id,
                "agent_run_id": agent_run_id,
                "customer_id": customer_id,
                "brief_id": brief_id,
                "status": status,
                "skip_reason": skip_reason,
            },
        )

        logger.info(
            "deal_marked_processed",
            notion_deal_id=notion_deal_id,
            status=status,
        )

        return record

    async def _is_deal_processed(self, notion_deal_id: str) -> bool:
        """
        Check if a deal has already been processed.

        Args:
            notion_deal_id: Notion page ID

        Returns:
            True if already processed
        """
        row = await self.db.query_one(
            """
            SELECT id FROM processed_deals
            WHERE workspace_id = $1 AND notion_deal_id = $2
            """,
            [self.workspace_id, notion_deal_id],
        )
        return row is not None

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
        return await self.db.query_all(
            """
            SELECT pd.*, c.name as customer_name
            FROM processed_deals pd
            LEFT JOIN customers c ON pd.customer_id = c.id
            WHERE pd.workspace_id = $1
            ORDER BY pd.processed_at DESC
            LIMIT $2 OFFSET $3
            """,
            [self.workspace_id, limit, offset],
        )


    async def poll_and_sync(self) -> dict[str, Any]:
        """
        Poll Notion for new closed deals and trigger handoff workflows.

        This is the main entry point for the polling system.

        Returns:
            Summary of what was processed:
            - new_deals: Number of new deals found
            - triggered_agents: Number of handoff agents triggered
        """
        from core.logging import get_logger

        logger = get_logger("NotionService")

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
        from core.logging import get_logger

        logger = get_logger("NotionService")

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
            await self.db.execute(
                """
                UPDATE processed_deals
                SET status = 'failed', skip_reason = $3
                WHERE workspace_id = $1 AND notion_deal_id = $2
                """,
                [self.workspace_id, deal.page_id, str(e)[:500]],
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

"""
Customer Service
Business logic for customer creation and management
"""

from typing import Any

from db.client import DatabaseClient
from core.logging import get_logger

logger = get_logger("CustomerService")


class CustomerService:
    """Service for customer-related business logic."""

    def __init__(self, db: DatabaseClient, workspace_id: str):
        self.db = db
        self.workspace_id = workspace_id

    async def create_from_deal(
        self,
        deal_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Create a customer from deal data.

        Args:
            deal_data: Extracted deal information from Notion

        Returns:
            Created customer record
        """
        company_name = deal_data.get("company_name", "Unknown Company")
        slug = self._generate_slug(company_name)

        # Check if customer already exists by slug
        existing = await self.db.query_one(
            """
            SELECT * FROM customers
            WHERE workspace_id = $1 AND slug = $2
            """,
            [self.workspace_id, slug],
        )

        if existing:
            logger.info(
                "customer_already_exists",
                customer_id=str(existing["id"]),
                slug=slug,
            )
            return existing

        # Create new customer
        customer = await self.db.insert(
            "customers",
            {
                "workspace_id": self.workspace_id,
                "name": company_name,
                "slug": slug,
                "one_liner": deal_data.get("notes"),
                "tier": self._determine_tier(deal_data.get("arr_cents", 0)),
                "arr_cents": deal_data.get("arr_cents"),
                "lifecycle": "handoff",
                "onboarding_day_current": 0,
            },
        )

        logger.info(
            "customer_created",
            customer_id=str(customer["id"]),
            name=company_name,
            lifecycle="handoff",
        )

        # Create stakeholders
        stakeholders = deal_data.get("stakeholders", [])
        for stakeholder in stakeholders:
            await self._create_stakeholder(customer["id"], stakeholder)

        return customer

    async def _create_stakeholder(
        self, customer_id: str, stakeholder_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a stakeholder for a customer."""
        stakeholder = await self.db.insert(
            "stakeholders",
            {
                "workspace_id": self.workspace_id,
                "customer_id": customer_id,
                "name": stakeholder_data.get("name", "Unknown"),
                "email": stakeholder_data.get("email"),
                "role": stakeholder_data.get("role"),
                "status": "active",
            },
        )

        logger.info(
            "stakeholder_created",
            stakeholder_id=str(stakeholder["id"]),
            customer_id=str(customer_id),
            role=stakeholder_data.get("role"),
        )

        return stakeholder

    async def get_by_id(self, customer_id: str) -> dict[str, Any] | None:
        """Get a customer by ID."""
        return await self.db.query_one(
            """
            SELECT * FROM customers
            WHERE id = $1 AND workspace_id = $2
            """,
            [customer_id, self.workspace_id],
        )

    async def get_by_slug(self, slug: str) -> dict[str, Any] | None:
        """Get a customer by slug."""
        return await self.db.query_one(
            """
            SELECT * FROM customers
            WHERE slug = $1 AND workspace_id = $2
            """,
            [slug, self.workspace_id],
        )

    async def update_lifecycle(
        self, customer_id: str, lifecycle: str
    ) -> dict[str, Any] | None:
        """Update a customer's lifecycle stage."""
        customer = await self.db.update(
            "customers",
            customer_id,
            {"lifecycle": lifecycle},
        )

        if customer:
            logger.info(
                "customer_lifecycle_updated",
                customer_id=customer_id,
                lifecycle=lifecycle,
            )

        return customer

    def _generate_slug(self, name: str) -> str:
        """Generate a URL-safe slug from company name."""
        slug = name.lower()
        slug = slug.replace(" ", "-")
        slug = slug.replace(".", "")
        slug = slug.replace(",", "")
        slug = "".join(c for c in slug if c.isalnum() or c == "-")
        return slug[:50]

    def _determine_tier(self, arr_cents: int) -> str:
        """Determine customer tier based on ARR."""
        if arr_cents >= 20000000:  # $200K+
            return "Enterprise"
        elif arr_cents >= 5000000:  # $50K+
            return "Mid-Market"
        elif arr_cents >= 1000000:  # $10K+
            return "Growth"
        else:
            return "Startup"

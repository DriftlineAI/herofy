"""
Customer Service (DataConnect Version)
Business logic for customer creation and management using Firebase Data Connect
"""

from typing import Any

from db.dataconnect_client import DataConnectClient
from core.logging import get_logger

logger = get_logger("CustomerServiceDC")


class CustomerServiceDC:
    """Service for customer-related business logic using DataConnect."""

    def __init__(self, dc: DataConnectClient, workspace_id: str):
        self.dc = dc
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
        result = await self.dc.execute_query(
            "GetCustomerBySlug",
            {
                "workspaceId": self.workspace_id,
                "slug": slug,
            },
        )

        customers = result.get("customers", [])
        if customers:
            existing = customers[0]
            logger.info(
                "customer_already_exists",
                customer_id=str(existing["id"]),
                slug=slug,
            )
            return existing

        # Create new customer
        customer_result = await self.dc.execute_mutation(
            "CreateCustomer",
            {
                "workspaceId": self.workspace_id,
                "name": company_name,
                "slug": slug,
                "oneLiner": deal_data.get("notes"),
                "tier": self._determine_tier(deal_data.get("arr_cents", 0)),
                "arrCents": deal_data.get("arr_cents"),
                "lifecycle": "handoff",
            },
        )

        customer = customer_result.get("customer_insert", {})

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
        stakeholder_result = await self.dc.execute_mutation(
            "CreateStakeholderPublic",
            {
                "workspaceId": self.workspace_id,
                "customerId": customer_id,
                "name": stakeholder_data.get("name", "Unknown"),
                "email": stakeholder_data.get("email"),
                "role": stakeholder_data.get("role"),
            },
        )

        stakeholder = stakeholder_result.get("stakeholder_insert", {})

        logger.info(
            "stakeholder_created",
            stakeholder_id=str(stakeholder["id"]),
            customer_id=str(customer_id),
            role=stakeholder_data.get("role"),
        )

        return stakeholder

    async def get_by_id(self, customer_id: str) -> dict[str, Any] | None:
        """Get a customer by ID."""
        result = await self.dc.execute_query(
            "GetCustomerPublic",
            {"id": customer_id},
        )
        return result.get("customer")

    async def get_by_slug(self, slug: str) -> dict[str, Any] | None:
        """Get a customer by slug."""
        result = await self.dc.execute_query(
            "GetCustomerBySlug",
            {
                "workspaceId": self.workspace_id,
                "slug": slug,
            },
        )
        customers = result.get("customers", [])
        return customers[0] if customers else None

    async def update_lifecycle(
        self, customer_id: str, lifecycle: str
    ) -> dict[str, Any] | None:
        """Update a customer's lifecycle stage."""
        result = await self.dc.execute_mutation(
            "UpdateCustomerLifecycle",
            {
                "id": customer_id,
                "lifecycle": lifecycle,
            },
        )

        customer = result.get("customer_update", {})

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

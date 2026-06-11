"""
Customer Factory

Deterministic factory for creating Customer records from external sources.
This is infrastructure-level code that runs BEFORE autonomous agents.

Architecture:
  Poll → CustomerFactory → Enrichment → Autonomous Agent

The CustomerFactory handles:
- Field mapping from external sources (Notion, etc.)
- Slug generation
- Lifecycle mapping to valid enum values
- Stakeholder creation
- Deduplication checks

It does NOT handle:
- AI inference (that's EnrichmentService)
- Plans or milestones (that's the autonomous agent)
- HITL questions (that's the autonomous agent)

Usage:
    from services.customer_factory import CustomerFactory

    factory = CustomerFactory(workspace_id)
    customer_id = await factory.create_from_notion(
        notion_deal_id="page-123",
        properties={"Company": {"title": [{"text": {"content": "Acme"}}]}, ...},
        field_mappings={"Company": "name", "Lifecycle": "lifecycle"},
    )
"""

import re
from typing import Any

from db.dataconnect_client import get_dataconnect_client, DataConnectClient
from core.logging import get_logger

logger = get_logger("CustomerFactory")


# Valid CustomerLifecycle enum values
VALID_LIFECYCLES = {
    "prospect",
    "handoff",
    "onboarding",
    "active",
    "renewing",
    "at_risk",
    "churned",
}

# Map common variations to valid lifecycle values
LIFECYCLE_MAP = {
    # Exact enum matches
    "prospect": "prospect",
    "handoff": "handoff",
    "onboarding": "onboarding",
    "active": "active",
    "renewing": "renewing",
    "at_risk": "at_risk",
    "at risk": "at_risk",
    "atrisk": "at_risk",
    "churned": "churned",
    # Common variations -> prospect
    "lead": "prospect",
    "trial": "prospect",
    "demo": "prospect",
    "evaluating": "prospect",
    "pipeline": "prospect",
    # Common variations -> handoff
    "handover": "handoff",
    "hand off": "handoff",
    "hand-off": "handoff",
    "transitioning": "handoff",
    "new": "handoff",
    "won": "handoff",
    "closed won": "handoff",
    "closed-won": "handoff",
    # Common variations -> onboarding
    "implementation": "onboarding",
    "implementing": "onboarding",
    "setup": "onboarding",
    "kickoff": "onboarding",
    "kick-off": "onboarding",
    # Common variations -> active
    "live": "active",
    "customer": "active",
    "paying": "active",
    "subscribed": "active",
    "current": "active",
    # Common variations -> renewing
    "renewal": "renewing",
    "up for renewal": "renewing",
    "expiring": "renewing",
    # Common variations -> at_risk
    "risk": "at_risk",
    "at-risk": "at_risk",
    "warning": "at_risk",
    "unhappy": "at_risk",
    # Common variations -> churned
    "churn": "churned",
    "cancelled": "churned",
    "canceled": "churned",
    "lost": "churned",
    "closed lost": "churned",
    "closed-lost": "churned",
    "inactive": "churned",
}


class CustomerFactory:
    """
    Factory for creating Customer records from external sources.

    This is deterministic infrastructure - no AI inference happens here.
    """

    def __init__(self, workspace_id: str, dc: DataConnectClient | None = None):
        """
        Initialize the factory.

        Args:
            workspace_id: The workspace to create customers in
            dc: Optional DataConnect client (uses global if not provided)
        """
        self.workspace_id = workspace_id
        self.dc = dc or get_dataconnect_client()

    async def create_from_notion(
        self,
        notion_deal_id: str,
        properties: dict[str, Any],
        field_mappings: dict[str, str] | None = None,
    ) -> str:
        """
        Create a customer from Notion deal properties.

        Args:
            notion_deal_id: The Notion page ID
            properties: Raw Notion properties dict
            field_mappings: Mapping of Notion property names to Herofy fields
                           e.g., {"Company Name": "name", "Lifecycle Stage": "lifecycle"}

        Returns:
            Customer ID of created customer

        Raises:
            ValueError: If required fields are missing
        """
        mappings = field_mappings or {}

        # Extract fields using mappings
        customer_data: dict[str, Any] = {
            "workspaceId": self.workspace_id,
            "lifecycle": "handoff",  # Default for new deals from CRM
            "enrichmentStatus": "pending",
            "externalSource": "notion",
            "externalId": notion_deal_id,
        }

        stakeholder_data: dict[str, Any] = {}
        raw_notes_parts: list[str] = []

        for notion_prop, herofy_field in mappings.items():
            if notion_prop not in properties:
                continue

            value = self._parse_notion_property(properties[notion_prop])
            if value is None or value == "":
                continue

            if herofy_field == "name":
                customer_data["name"] = str(value)
            elif herofy_field == "oneLiner":
                customer_data["oneLiner"] = str(value)
            elif herofy_field == "tier":
                customer_data["tier"] = str(value)
            elif herofy_field == "arr":
                try:
                    arr_dollars = float(value) if value else 0
                    customer_data["arrCents"] = int(arr_dollars * 100)
                except (ValueError, TypeError):
                    pass
            elif herofy_field == "lifecycle":
                mapped = self._map_lifecycle(str(value))
                if mapped:
                    customer_data["lifecycle"] = mapped
            elif herofy_field == "stakeholderName":
                stakeholder_data["name"] = str(value)
            elif herofy_field == "stakeholderEmail":
                stakeholder_data["email"] = str(value)
            elif herofy_field == "stakeholderRole":
                stakeholder_data["role"] = str(value)
            elif herofy_field == "rawNotes":
                raw_notes_parts.append(str(value))
            else:
                # Unmapped field - add to raw notes
                raw_notes_parts.append(f"{notion_prop}: {value}")

        # Combine raw notes
        if raw_notes_parts:
            customer_data["rawNotes"] = "\n\n".join(raw_notes_parts)

        # Validate required fields
        if not customer_data.get("name"):
            raise ValueError("Customer name is required")

        # Generate slug
        customer_data["slug"] = self._generate_slug(customer_data["name"])

        # Check for existing customer
        existing = await self._get_existing_customer(notion_deal_id)
        if existing:
            logger.info(
                "customer_already_exists",
                external_id=notion_deal_id,
                customer_id=existing["id"],
            )
            return existing["id"]

        # Create customer
        result = await self.dc.execute_mutation(
            "CreateCustomer",
            customer_data,
        )

        customer_id = result.get("customer_insert", {}).get("id")
        if not customer_id:
            raise ValueError("Failed to create customer - no ID returned")

        logger.info(
            "customer_created",
            customer_id=customer_id,
            name=customer_data["name"],
            external_source="notion",
            external_id=notion_deal_id,
        )

        # Create stakeholder if we have data
        if stakeholder_data.get("name"):
            await self._create_stakeholder(customer_id, stakeholder_data)

        return customer_id

    async def create_from_raw(
        self,
        name: str,
        external_source: str = "manual",
        external_id: str | None = None,
        lifecycle: str = "handoff",
        tier: str | None = None,
        arr_cents: int | None = None,
        one_liner: str | None = None,
        raw_notes: str | None = None,
        stakeholder_name: str | None = None,
        stakeholder_email: str | None = None,
        stakeholder_role: str | None = None,
    ) -> str:
        """
        Create a customer from raw field values.

        Used for direct creation or other integration sources.

        Args:
            name: Customer name (required)
            external_source: Source system (notion, salesforce, manual, etc.)
            external_id: ID in source system
            lifecycle: Lifecycle stage
            tier: Customer tier
            arr_cents: Annual recurring revenue in cents
            one_liner: Brief description
            raw_notes: Raw notes for enrichment
            stakeholder_name: Primary stakeholder name
            stakeholder_email: Primary stakeholder email
            stakeholder_role: Primary stakeholder role

        Returns:
            Customer ID
        """
        # Map lifecycle
        mapped_lifecycle = self._map_lifecycle(lifecycle) or "handoff"

        customer_data: dict[str, Any] = {
            "workspaceId": self.workspace_id,
            "name": name,
            "slug": self._generate_slug(name),
            "lifecycle": mapped_lifecycle,
            "enrichmentStatus": "pending",
            "externalSource": external_source,
        }

        if external_id:
            customer_data["externalId"] = external_id
        if tier:
            customer_data["tier"] = tier
        if arr_cents is not None:
            customer_data["arrCents"] = arr_cents
        if one_liner:
            customer_data["oneLiner"] = one_liner
        if raw_notes:
            customer_data["rawNotes"] = raw_notes

        # Check for existing customer by external_id
        if external_id:
            existing = await self._get_existing_customer(external_id)
            if existing:
                logger.info(
                    "customer_already_exists",
                    external_id=external_id,
                    customer_id=existing["id"],
                )
                return existing["id"]

        # Create customer
        result = await self.dc.execute_mutation(
            "CreateCustomer",
            customer_data,
        )

        customer_id = result.get("customer_insert", {}).get("id")
        if not customer_id:
            raise ValueError("Failed to create customer - no ID returned")

        logger.info(
            "customer_created",
            customer_id=customer_id,
            name=name,
            external_source=external_source,
            external_id=external_id,
        )

        # Create stakeholder if provided
        if stakeholder_name:
            await self._create_stakeholder(
                customer_id,
                {
                    "name": stakeholder_name,
                    "email": stakeholder_email,
                    "role": stakeholder_role,
                },
            )

        return customer_id

    async def _get_existing_customer(self, external_id: str) -> dict | None:
        """Check if a customer already exists with this external_id."""
        try:
            result = await self.dc.execute_query(
                "GetCustomerByExternalId",
                {
                    "workspaceId": self.workspace_id,
                    "externalId": external_id,
                },
            )
            customers = result.get("customers", [])
            return customers[0] if customers else None
        except Exception as e:
            logger.warning(
                "existing_customer_check_failed",
                external_id=external_id,
                error=str(e),
            )
            return None

    async def _create_stakeholder(
        self,
        customer_id: str,
        data: dict[str, Any],
    ) -> str | None:
        """Create a stakeholder for a customer."""
        if not data.get("name"):
            return None

        try:
            result = await self.dc.execute_mutation(
                "CreateStakeholder",
                {
                    "workspaceId": self.workspace_id,
                    "customerId": customer_id,
                    "name": data["name"],
                    "email": data.get("email"),
                    "role": data.get("role"),
                },
            )
            stakeholder_id = result.get("stakeholder_insert", {}).get("id")

            logger.info(
                "stakeholder_created",
                stakeholder_id=stakeholder_id,
                customer_id=customer_id,
                name=data["name"],
            )

            return stakeholder_id
        except Exception as e:
            logger.warning(
                "stakeholder_create_failed",
                customer_id=customer_id,
                name=data.get("name"),
                error=str(e),
            )
            return None

    def _parse_notion_property(self, prop: Any) -> Any:
        """
        Parse a Notion property value.

        Handles both:
        - Raw Notion property objects (dicts with "type" key)
        - Already-extracted values (strings, numbers, booleans, lists)

        The NotionEventEmitter extracts values before creating events,
        so we need to handle both formats.
        """
        if prop is None:
            return None

        # If it's already a simple value (extracted by NotionEventEmitter), return it
        if isinstance(prop, (str, int, float, bool)):
            return prop

        if isinstance(prop, list):
            # Could be a list of strings (multi-select) or other values
            return ", ".join(str(v) for v in prop if v)

        if not isinstance(prop, dict):
            return str(prop)

        prop_type = prop.get("type")

        # If no type field, it's not a raw Notion property - return as-is
        if prop_type is None:
            return prop

        if prop_type == "title":
            title_list = prop.get("title", [])
            if title_list:
                return "".join(t.get("plain_text", "") for t in title_list)
            return None

        if prop_type == "rich_text":
            text_list = prop.get("rich_text", [])
            if text_list:
                return "".join(t.get("plain_text", "") for t in text_list)
            return None

        if prop_type == "number":
            return prop.get("number")

        if prop_type == "select":
            select = prop.get("select")
            if select:
                return select.get("name")
            return None

        if prop_type == "multi_select":
            multi = prop.get("multi_select", [])
            if multi:
                return ", ".join(s.get("name", "") for s in multi if s.get("name"))
            return None

        if prop_type == "status":
            status = prop.get("status")
            if status:
                return status.get("name")
            return None

        if prop_type == "date":
            date = prop.get("date")
            if date:
                return date.get("start")
            return None

        if prop_type == "email":
            return prop.get("email")

        if prop_type == "phone_number":
            return prop.get("phone_number")

        if prop_type == "url":
            return prop.get("url")

        if prop_type == "checkbox":
            return prop.get("checkbox")

        if prop_type == "people":
            people = prop.get("people", [])
            if people:
                return ", ".join(p.get("name", "") for p in people if p.get("name"))
            return None

        if prop_type == "relation":
            relations = prop.get("relation", [])
            if relations:
                return [r.get("id") for r in relations if r.get("id")]
            return None

        if prop_type == "rollup":
            rollup = prop.get("rollup", {})
            rollup_type = rollup.get("type")
            if rollup_type == "number":
                return rollup.get("number")
            if rollup_type == "array":
                arr = rollup.get("array", [])
                return [self._parse_notion_property(item) for item in arr]
            return None

        if prop_type == "formula":
            formula = prop.get("formula", {})
            formula_type = formula.get("type")
            if formula_type in ("string", "number", "boolean", "date"):
                return formula.get(formula_type)
            return None

        # Unknown type - return as-is
        return prop.get(prop_type)

    def _map_lifecycle(self, value: str) -> str | None:
        """Map a lifecycle value to a valid enum value."""
        if not value:
            return None

        normalized = value.lower().strip()
        mapped = LIFECYCLE_MAP.get(normalized)

        if mapped:
            logger.debug(
                "lifecycle_mapped",
                raw_value=value,
                mapped_value=mapped,
            )
        else:
            logger.warning(
                "unmapped_lifecycle_value",
                value=value,
            )

        return mapped

    def _generate_slug(self, name: str) -> str:
        """Generate a URL-safe slug from a name."""
        return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

"""
Notion Tool for ADK Agents
MCP client wrapper for Notion operations (with mock fallback)
"""

from typing import Any

from config import settings
from core.errors import (
    NotionToolError,
    IntegrationNotConfiguredError,
    IntegrationAuthError,
)
from core.logging import get_logger
from core.types import IntegrationType

logger = get_logger("NotionTool")

# Default property mappings (reasonable defaults for common Notion structures)
# Each key maps to a list of candidate property names to try in order
DEFAULT_PROPERTY_MAPPING = {
    "company_name": ["Name", "Company", "Company Name", "Account", "Title"],
    "arr_cents": ["ARR", "Value", "Deal Value", "Contract Value", "Amount"],
    "timeline": ["Timeline", "Close Date", "Target Date", "Due Date"],
    "sales_commitments": ["Commitments", "Sales Commitments", "Promises", "Agreements"],
    "technical_context": ["Technical", "Technical Requirements", "Tech Notes", "Requirements"],
    "stakeholders": ["Contacts", "Stakeholders", "Team", "People"],
    "notes": ["Notes", "Description", "Details", "Summary"],
}


async def read_notion_deal(
    deal_id: str,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """
    Read a Notion deal page and extract structured data.

    Args:
        deal_id: The Notion page ID for the deal
        workspace_id: Workspace ID for OAuth token lookup (required for real API)

    Returns:
        dict: Extracted deal data including:
            - company_name: Company name
            - arr_cents: Annual recurring revenue in cents
            - sales_commitments: List of commitments made during sales
            - technical_context: Technical requirements and constraints
            - stakeholders: List of stakeholder contacts
            - timeline: Expected timeline notes
            - notes: Additional notes from page body
    """
    if settings.use_mock_notion:
        logger.info("using_mock_notion_data", deal_id=deal_id)
        return _get_mock_deal_data(deal_id)

    # Real Notion API implementation
    try:
        return await _fetch_notion_deal(deal_id, workspace_id)
    except IntegrationNotConfiguredError:
        logger.info(
            "source_skipped",
            workspace_id=workspace_id,
            source="notion",
            reason="not_configured",
        )
        return {"error": "Notion integration not configured"}
    except IntegrationAuthError as e:
        logger.info(
            "source_skipped",
            workspace_id=workspace_id,
            source="notion",
            reason="auth_failed",
            error=str(e),
        )
        return {"error": "Notion authentication failed - reconnection required"}
    except Exception as e:
        logger.error("notion_fetch_failed", deal_id=deal_id, error=str(e))
        raise NotionToolError(f"Failed to read Notion deal {deal_id}: {e}")


async def _fetch_notion_deal(
    deal_id: str,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """
    Fetch deal data from Notion via API.

    Args:
        deal_id: Notion page ID
        workspace_id: Workspace ID for token lookup

    Returns:
        Parsed deal data
    """
    if not workspace_id:
        logger.warning("notion_fetch_no_workspace", deal_id=deal_id)
        return _get_mock_deal_data(deal_id)

    # Import here to avoid circular imports
    from db.dataconnect_client import get_dataconnect_client
    from services.integration_service_dc import IntegrationServiceDC
    from integrations.clients.notion_client import NotionClient, NotionAPIError

    dc = get_dataconnect_client()
    integration_service = IntegrationServiceDC(dc, workspace_id)
    client = NotionClient(integration_service)

    try:
        # Get custom property mapping from workspace config (if set)
        integration = await integration_service.get_integration(IntegrationType.NOTION)
        custom_mapping: dict[str, list[str]] = {}
        if integration:
            config = integration.get("config", {})
            # Config might be a JSON string that needs parsing
            if isinstance(config, str):
                try:
                    import json
                    config = json.loads(config)
                except (json.JSONDecodeError, TypeError):
                    config = {}
            if isinstance(config, dict):
                custom_mapping = config.get("property_mapping", {})

        # Merge custom mapping with defaults (custom takes precedence)
        property_mapping = {**DEFAULT_PROPERTY_MAPPING}
        for key, candidates in custom_mapping.items():
            if isinstance(candidates, list):
                property_mapping[key] = candidates

        # Fetch page and child blocks
        page = await client.get_page(deal_id)
        blocks = await client.get_block_children(deal_id)

        # Parse with flexible property detection
        return _parse_notion_deal_page(page, blocks, property_mapping)

    except NotionAPIError as e:
        logger.error(
            "notion_api_error",
            deal_id=deal_id,
            error=str(e),
            code=e.code,
        )
        return {"error": str(e)}
    finally:
        await client.cleanup()


def _parse_notion_deal_page(
    page: dict[str, Any],
    blocks: dict[str, Any],
    property_mapping: dict[str, list[str]],
) -> dict[str, Any]:
    """
    Parse Notion page with flexible property detection.

    Tries each candidate property name in order until one matches with a non-empty value.

    Args:
        page: Notion page object
        blocks: Page children blocks
        property_mapping: Mapping of field names to candidate property names

    Returns:
        Parsed deal data
    """
    props = page.get("properties", {})

    def find_property(key: str) -> Any:
        """Find property value by trying candidate names until a non-empty value is found."""
        candidates = property_mapping.get(key, [key])
        for candidate in candidates:
            if candidate in props:
                value = _extract_property_value(props[candidate])
                # Only return if value is non-empty (not None, not empty/whitespace string, not empty list)
                # Note: 0 and False are considered valid values
                if value is None:
                    continue
                if isinstance(value, str) and not value.strip():
                    continue
                if value == []:
                    continue
                return value
        return None

    # Parse ARR to cents
    arr_value = find_property("arr_cents")
    arr_cents = _to_cents(arr_value)

    # Parse commitments (could be multi-select, rich_text, or relation)
    commitments_raw = find_property("sales_commitments")
    sales_commitments = _parse_list_property(commitments_raw)

    # Parse technical context
    technical_raw = find_property("technical_context")
    technical_context = _parse_list_property(technical_raw)

    # Parse stakeholders (could be people, relation, or rich_text)
    stakeholders_raw = find_property("stakeholders")
    stakeholders = _parse_stakeholders(stakeholders_raw)

    return {
        "company_name": find_property("company_name") or "Unknown",
        "arr_cents": arr_cents,
        "timeline": find_property("timeline"),
        "sales_commitments": sales_commitments,
        "technical_context": technical_context,
        "stakeholders": stakeholders,
        "notes": _extract_body_text(blocks),
    }


def _extract_property_value(prop: dict[str, Any]) -> Any:
    """
    Extract value from a Notion property based on its type.

    Args:
        prop: Notion property object

    Returns:
        Extracted value
    """
    prop_type = prop.get("type")

    if prop_type == "title":
        titles = prop.get("title", [])
        return "".join(t.get("plain_text", "") for t in titles)

    elif prop_type == "rich_text":
        texts = prop.get("rich_text", [])
        return "".join(t.get("plain_text", "") for t in texts)

    elif prop_type == "number":
        return prop.get("number")

    elif prop_type == "select":
        select = prop.get("select")
        return select.get("name") if select else None

    elif prop_type == "multi_select":
        return [s.get("name") for s in prop.get("multi_select", [])]

    elif prop_type == "date":
        date = prop.get("date")
        return date.get("start") if date else None

    elif prop_type == "checkbox":
        return prop.get("checkbox", False)

    elif prop_type == "email":
        return prop.get("email")

    elif prop_type == "url":
        return prop.get("url")

    elif prop_type == "phone_number":
        return prop.get("phone_number")

    elif prop_type == "people":
        people = prop.get("people", [])
        return [
            {
                "name": p.get("name", ""),
                "email": p.get("person", {}).get("email", ""),
            }
            for p in people
        ]

    elif prop_type == "relation":
        # TODO: Relation properties return only page IDs, not resolved data.
        # If Stakeholders is a relation to a People DB, HandoffChain gets opaque IDs
        # like ["page-abc-123"] instead of names, which degrades Gemini plan quality.
        # Fix: fetch related pages via client.get_page() for each ID, extract names.
        # For now, returning IDs - downstream code should handle gracefully.
        return [r.get("id") for r in prop.get("relation", [])]

    elif prop_type == "formula":
        formula = prop.get("formula", {})
        return formula.get(formula.get("type"))

    elif prop_type == "rollup":
        rollup = prop.get("rollup", {})
        return rollup.get(rollup.get("type"))

    return None


def _to_cents(value: Any) -> int | None:
    """
    Convert a value to cents.

    Args:
        value: Number or string representing dollars

    Returns:
        Value in cents or None
    """
    if value is None:
        return None

    try:
        if isinstance(value, str):
            # Remove currency symbols and commas
            value = value.replace("$", "").replace(",", "").strip()

        num = float(value)
        return int(num * 100)
    except (ValueError, TypeError):
        return None


def _parse_list_property(value: Any) -> list[dict[str, str]]:
    """
    Parse a list property into commitment/context format.

    Args:
        value: Property value (could be string, list, etc.)

    Returns:
        List of {item, details} dicts
    """
    if value is None:
        return []

    if isinstance(value, list):
        # Multi-select or people
        return [{"item": str(v), "details": ""} for v in value if v]

    if isinstance(value, str):
        # Rich text - split by newlines or bullets
        lines = value.replace("• ", "\n").replace("- ", "\n").split("\n")
        return [
            {"item": line.strip(), "details": ""}
            for line in lines
            if line.strip()
        ]

    return []


def _parse_stakeholders(value: Any) -> list[dict[str, str]]:
    """
    Parse stakeholders from various property formats.

    Args:
        value: Property value

    Returns:
        List of stakeholder dicts with name, email, role
    """
    if value is None:
        return []

    if isinstance(value, list):
        result = []
        for v in value:
            if isinstance(v, dict):
                result.append({
                    "name": v.get("name", ""),
                    "email": v.get("email", ""),
                    "role": v.get("role", ""),
                })
            elif isinstance(v, str):
                result.append({"name": v, "email": "", "role": ""})
        return result

    if isinstance(value, str):
        # Try to parse as comma-separated names
        names = [n.strip() for n in value.split(",") if n.strip()]
        return [{"name": n, "email": "", "role": ""} for n in names]

    return []


def _extract_body_text(blocks: dict[str, Any]) -> str:
    """
    Extract plain text from page body blocks.

    Args:
        blocks: Notion blocks response

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

    return "\n".join(texts)


def _get_mock_deal_data(deal_id: str) -> dict[str, Any]:
    """
    Return mock deal data for development and testing.
    This simulates what we'd extract from a real Notion deal page.
    """

    # Different mock data based on deal_id for testing variety
    if "techcorp" in deal_id.lower():
        return {
            "company_name": "TechCorp Solutions",
            "arr_cents": 5000000,  # $50K ARR
            "sales_commitments": [
                {
                    "item": "30-day implementation timeline",
                    "details": "CEO wants to launch before board meeting",
                },
                {
                    "item": "Dedicated support channel",
                    "details": "Slack Connect promised by sales",
                },
                {
                    "item": "Custom reporting dashboard",
                    "details": "Weekly exec summary report required",
                },
            ],
            "technical_context": [
                {
                    "item": "REST API integration required",
                    "details": "They use a custom CRM system",
                },
                {
                    "item": "SSO via Okta",
                    "details": "Standard enterprise requirement",
                },
                {
                    "item": "Data residency in US-East",
                    "details": "Compliance requirement",
                },
            ],
            "stakeholders": [
                {
                    "name": "Alex Rivera",
                    "email": "alex@techcorp.io",
                    "role": "CEO",
                },
                {
                    "name": "Jordan Park",
                    "email": "jordan@techcorp.io",
                    "role": "VP Engineering",
                },
            ],
            "timeline": "Must launch before Q2 board meeting (30 days from close)",
            "notes": "High urgency deal. CEO is very involved. Technical team is capable but stretched thin.",
        }

    # Default mock data
    return {
        "company_name": f"Company from {deal_id[:8]}",
        "arr_cents": 7500000,  # $75K ARR
        "sales_commitments": [
            {
                "item": "45-day implementation",
                "details": "Standard timeline agreed",
            },
            {
                "item": "Quarterly business reviews",
                "details": "Exec sponsor requested regular check-ins",
            },
        ],
        "technical_context": [
            {
                "item": "API integration",
                "details": "Standard REST API setup",
            },
            {
                "item": "Single sign-on",
                "details": "Azure AD integration needed",
            },
        ],
        "stakeholders": [
            {
                "name": "Jane Doe",
                "email": "jane@example.com",
                "role": "Head of Operations",
            },
            {
                "name": "John Smith",
                "email": "john@example.com",
                "role": "Technical Lead",
            },
        ],
        "timeline": "Standard 45-day implementation",
        "notes": "Standard mid-market deal with typical requirements.",
    }


# =============================================================================
# Future: List closed deals for SignalWatcher
# =============================================================================


async def list_closed_deals(
    workspace_id: str | None = None,
    since_timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """
    List recently closed deals from Notion.
    Used by HandoffAuto agent to detect new handoffs.

    Args:
        workspace_id: Workspace ID for OAuth token lookup
        since_timestamp: Only return deals closed after this time (ISO format)

    Returns:
        list: List of deal summaries with page_id, company_name, closed_at
    """
    if settings.use_mock_notion:
        logger.info("using_mock_closed_deals", since=since_timestamp)

        # Return different mock data based on whether this is a fresh poll
        # or an incremental poll
        from datetime import datetime, timedelta

        mock_deals = [
            {
                "page_id": "notion-deal-techcorp-001",
                "company_name": "TechCorp Solutions",
                "closed_at": (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z",
                "arr_cents": 5000000,
                "timeline": "30 days from close",
                "sales_commitments": [
                    {"item": "Dedicated support channel", "details": "Slack Connect"},
                    {"item": "30-day implementation", "details": "CEO deadline"},
                ],
                "technical_context": [
                    {"item": "REST API integration", "details": "Custom CRM"},
                    {"item": "SSO via Okta", "details": "Enterprise requirement"},
                ],
                "stakeholders": [
                    {"name": "Alex Rivera", "email": "alex@techcorp.io", "role": "CEO"},
                    {"name": "Jordan Park", "email": "jordan@techcorp.io", "role": "VP Engineering"},
                ],
            },
            {
                "page_id": "notion-deal-acme-002",
                "company_name": "Acme Corp",
                "closed_at": (datetime.utcnow() - timedelta(hours=2)).isoformat() + "Z",
                "arr_cents": 7500000,
                "timeline": "Standard 45-day implementation",
                "sales_commitments": [
                    {"item": "Quarterly business reviews", "details": "Exec sponsor requested"},
                ],
                "technical_context": [
                    {"item": "Azure AD SSO", "details": "Standard setup"},
                ],
                "stakeholders": [
                    {"name": "Jane Smith", "email": "jane@acme.com", "role": "Head of Ops"},
                ],
            },
        ]

        # Filter by timestamp if provided
        if since_timestamp:
            try:
                since_dt = datetime.fromisoformat(since_timestamp.replace("Z", "+00:00"))
                mock_deals = [
                    d for d in mock_deals
                    if datetime.fromisoformat(d["closed_at"].replace("Z", "+00:00")) > since_dt
                ]
            except (ValueError, TypeError):
                pass

        return mock_deals

    # Real Notion API implementation
    if not workspace_id:
        logger.warning("list_closed_deals_no_workspace")
        return []

    try:
        return await _fetch_closed_deals_from_notion(workspace_id, since_timestamp)
    except IntegrationNotConfiguredError:
        logger.info(
            "source_skipped",
            workspace_id=workspace_id,
            source="notion",
            reason="not_configured",
        )
        return []
    except IntegrationAuthError as e:
        logger.warning(
            "source_skipped",
            workspace_id=workspace_id,
            source="notion",
            reason="auth_failed",
            error=str(e),
        )
        return []
    except Exception as e:
        logger.error("list_closed_deals_failed", workspace_id=workspace_id, error=str(e))
        return []


async def _fetch_closed_deals_from_notion(
    workspace_id: str,
    since_timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch closed deals from Notion via API.

    Args:
        workspace_id: Workspace ID for token lookup
        since_timestamp: Filter by last_edited_time if provided

    Returns:
        List of parsed deals
    """
    from db.dataconnect_client import get_dataconnect_client
    from services.integration_service_dc import IntegrationServiceDC
    from integrations.clients.notion_client import NotionClient
    from core.types import IntegrationType
    import json

    dc = get_dataconnect_client()
    integration_service = IntegrationServiceDC(dc, workspace_id)
    client = NotionClient(integration_service)

    try:
        # Get integration config for database ID and field mappings
        integration = await integration_service.get_integration(IntegrationType.NOTION)
        if not integration:
            raise IntegrationNotConfiguredError(workspace_id, "notion")

        config = integration.get("config", {})
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except (json.JSONDecodeError, TypeError):
                config = {}

        database_id = config.get("database_id")
        if not database_id:
            raise IntegrationNotConfiguredError(workspace_id, "notion")

        # Determine poll mode:
        # - "status_filter": Filter by status_field = closed_value (sales pipeline)
        # - "all_new": Poll all records, dedupe by processed_deals table (customer database)
        #
        # Default to "all_new" if no status filtering is configured
        poll_mode = config.get("poll_mode", "all_new")
        status_field = config.get("status_field")
        closed_value = config.get("closed_value")

        # If status_field and closed_value are set, use status_filter mode
        if status_field and closed_value:
            poll_mode = "status_filter"

        logger.info(
            "notion_poll_config",
            workspace_id=workspace_id,
            database_id=database_id,
            poll_mode=poll_mode,
            status_field=status_field,
            closed_value=closed_value,
        )

        # Build filter based on poll mode
        filter_obj: dict[str, Any] | None = None

        if poll_mode == "status_filter":
            # Sales pipeline mode: filter by status
            filter_obj = {
                "property": status_field,
                "status": {"equals": closed_value},
            }
            # Add timestamp filter if available
            if since_timestamp:
                filter_obj = {
                    "and": [
                        {"property": status_field, "status": {"equals": closed_value}},
                        {"timestamp": "last_edited_time", "last_edited_time": {"after": since_timestamp}},
                    ]
                }
        else:
            # all_new mode: no status filter, just get recent records
            # Deduplication happens in NotionServiceDC via processed_deals table
            if since_timestamp:
                filter_obj = {
                    "timestamp": "last_edited_time",
                    "last_edited_time": {"after": since_timestamp},
                }
            # If no since_timestamp, filter_obj stays None (query all records)

        # Query the database
        logger.info(
            "notion_poll_query",
            workspace_id=workspace_id,
            poll_mode=poll_mode,
            filter=filter_obj,
        )

        # Build query kwargs
        query_kwargs: dict[str, Any] = {
            "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}],
            "page_size": 50,
        }
        if filter_obj:
            query_kwargs["filter"] = filter_obj

        result = await client.query_database(database_id, **query_kwargs)

        logger.info(
            "notion_poll_result",
            workspace_id=workspace_id,
            result_count=len(result.get("results", [])),
            has_more=result.get("has_more", False),
        )

        # Parse results
        deals = []
        for page in result.get("results", []):
            deal = _parse_deal_from_page(page, config)
            if deal:
                deals.append(deal)

        logger.info(
            "closed_deals_fetched",
            workspace_id=workspace_id,
            count=len(deals),
            since=since_timestamp,
        )

        return deals

    finally:
        await client.cleanup()


def _parse_deal_from_page(
    page: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Parse a Notion page into a deal dict.

    Args:
        page: Notion page object
        config: Integration config with field mappings

    Returns:
        Parsed deal or None if invalid
    """
    props = page.get("properties", {})
    page_id = page.get("id")

    if not page_id:
        return None

    # Get custom field mappings or use defaults
    field_mappings = config.get("field_mappings", {})

    # Try to find company name
    company_name = None
    for prop_name in ["Name", "Company", "Company Name", "Account", "Title"]:
        if prop_name in props:
            company_name = _extract_property_value(props[prop_name])
            if company_name:
                break

    # If field mapping specifies a name field, use that
    if field_mappings.get("name") and field_mappings["name"] in props:
        company_name = _extract_property_value(props[field_mappings["name"]])

    if not company_name:
        company_name = f"Deal {page_id[:8]}"

    # Extract other fields
    arr_value = None
    for prop_name in ["ARR", "Value", "Deal Value", "Contract Value", "Amount"]:
        if prop_name in props:
            arr_value = _extract_property_value(props[prop_name])
            if arr_value is not None:
                break

    arr_cents = None
    if arr_value is not None:
        try:
            arr_cents = int(float(arr_value) * 100)
        except (ValueError, TypeError):
            pass

    return {
        "page_id": page_id,
        "company_name": company_name,
        "closed_at": page.get("last_edited_time"),
        "arr_cents": arr_cents,
        # Additional fields can be fetched separately via read_notion_deal
        "timeline": None,
        "sales_commitments": [],
        "technical_context": [],
        "stakeholders": [],
    }


# =============================================================================
# OAuth Flow Helpers (for autonomous agent setup)
# =============================================================================


def get_notion_oauth_url(
    workspace_id: str,
    redirect_uri: str,
    state: str | None = None,
) -> str:
    """
    Generate the Notion OAuth authorization URL.

    Args:
        workspace_id: Our workspace ID (stored in state)
        redirect_uri: Where to redirect after auth
        state: Optional state parameter for security

    Returns:
        URL to redirect user to for Notion OAuth
    """
    from urllib.parse import urlencode

    client_id = settings.notion_client_id
    if not client_id:
        logger.warning("notion_oauth_not_configured")
        return ""

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "owner": "user",
        "state": state or workspace_id,
    }

    return f"https://api.notion.com/v1/oauth/authorize?{urlencode(params)}"


async def exchange_notion_oauth_code(
    code: str,
    redirect_uri: str,
) -> dict[str, Any]:
    """
    Exchange OAuth code for access token.

    Args:
        code: Authorization code from Notion callback
        redirect_uri: Must match the original redirect_uri

    Returns:
        Token response with access_token, workspace_id, etc.
    """
    import httpx
    import base64

    client_id = settings.notion_client_id
    client_secret = settings.notion_client_secret

    if not client_id or not client_secret:
        logger.error("notion_oauth_not_configured")
        return {"error": "Notion OAuth not configured"}

    # Create Basic auth header
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.notion.com/v1/oauth/token",
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/json",
            },
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )

        if response.status_code != 200:
            logger.error(
                "notion_oauth_exchange_failed",
                status=response.status_code,
                body=response.text,
            )
            return {"error": f"OAuth exchange failed: {response.status_code}"}

        return response.json()


async def list_notion_databases(access_token: str) -> list[dict[str, Any]]:
    """
    List databases the user has access to (for database picker).

    Args:
        access_token: Notion OAuth access token

    Returns:
        List of databases with id, title, etc.
    """
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.notion.com/v1/search",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            },
            json={
                "filter": {"property": "object", "value": "database"},
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
            },
        )

        if response.status_code != 200:
            logger.error(
                "notion_search_failed",
                status=response.status_code,
            )
            return []

        data = response.json()
        databases = []

        for result in data.get("results", []):
            title_parts = result.get("title", [])
            title = "".join(part.get("plain_text", "") for part in title_parts)

            databases.append({
                "id": result["id"],
                "title": title or "Untitled Database",
                "url": result.get("url"),
                "last_edited": result.get("last_edited_time"),
            })

        return databases

"""
Notion API Client
Uses httpx for Notion API access.
"""

from typing import Any, TYPE_CHECKING, Union

import httpx

from core.logging import get_logger
from core.errors import IntegrationAuthError
from core.types import IntegrationType

if TYPE_CHECKING:
    from services.integration_service import IntegrationService
    from services.integration_service_dc import IntegrationServiceDC

logger = get_logger("NotionClient")

# Notion error codes that indicate auth failure
NOTION_AUTH_CODES = {
    "unauthorized",
    "invalid_token",
    "restricted_resource",
}


class NotionClient:
    """
    Notion API client.

    Docs: https://developers.notion.com/reference
    """

    BASE_URL = "https://api.notion.com/v1"
    NOTION_VERSION = "2022-06-28"

    def __init__(self, integration_service: "Union[IntegrationService, IntegrationServiceDC]"):
        """
        Initialize Notion client.

        Args:
            integration_service: Service for getting valid tokens (supports both legacy and DC versions)
        """
        self.integration_service = integration_service
        self._http_client: httpx.AsyncClient | None = None

    @property
    def http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def _get_headers(self) -> dict[str, str]:
        """Get authorization headers with valid token."""
        access_token = await self.integration_service.get_valid_token(
            IntegrationType.NOTION
        )
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Notion-Version": self.NOTION_VERSION,
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs,
    ) -> dict[str, Any]:
        """Make authenticated Notion API request."""
        headers = await self._get_headers()
        url = f"{self.BASE_URL}/{endpoint}"

        response = await self.http_client.request(
            method,
            url,
            headers=headers,
            **kwargs,
        )

        if response.status_code >= 400:
            error_data = response.json()
            error_code = error_data.get("code", "")
            logger.error(
                "notion_api_error",
                endpoint=endpoint,
                status=response.status_code,
                error=error_data,
            )
            # Map auth-related errors to IntegrationAuthError
            if response.status_code == 401 or error_code in NOTION_AUTH_CODES:
                raise IntegrationAuthError(
                    f"Notion auth failed: {error_data.get('message', 'Unauthorized')}",
                    provider="notion",
                    details={"code": error_code, "status": response.status_code},
                )
            raise NotionAPIError(
                error_data.get("message", "Unknown error"),
                error_code,
                response.status_code,
            )

        return response.json()

    async def query_database(
        self,
        database_id: str,
        filter: dict[str, Any] | None = None,
        sorts: list[dict[str, Any]] | None = None,
        page_size: int = 100,
        start_cursor: str | None = None,
    ) -> dict[str, Any]:
        """
        Query a Notion database.

        Args:
            database_id: Database ID
            filter: Filter object
            sorts: Sort configuration
            page_size: Results per page (max 100)
            start_cursor: Pagination cursor

        Returns:
            Dict with 'results' list and pagination info
        """
        body: dict[str, Any] = {
            "page_size": min(page_size, 100),
        }
        if filter:
            body["filter"] = filter
        if sorts:
            body["sorts"] = sorts
        if start_cursor:
            body["start_cursor"] = start_cursor

        data = await self._request(
            "POST",
            f"databases/{database_id}/query",
            json=body,
        )

        return {
            "results": data.get("results", []),
            "has_more": data.get("has_more", False),
            "next_cursor": data.get("next_cursor"),
        }

    async def get_page(self, page_id: str) -> dict[str, Any]:
        """
        Get a Notion page.

        Args:
            page_id: Page ID

        Returns:
            Page object with properties
        """
        return await self._request("GET", f"pages/{page_id}")

    async def get_database(self, database_id: str) -> dict[str, Any]:
        """
        Get database schema/metadata.

        Args:
            database_id: Database ID

        Returns:
            Database object with properties schema
        """
        return await self._request("GET", f"databases/{database_id}")

    async def create_page(
        self,
        parent: dict[str, Any],
        properties: dict[str, Any],
        children: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Create a new page.

        Args:
            parent: Parent (database_id or page_id)
            properties: Page properties
            children: Page content blocks

        Returns:
            Created page object
        """
        body: dict[str, Any] = {
            "parent": parent,
            "properties": properties,
        }
        if children:
            body["children"] = children

        data = await self._request("POST", "pages", json=body)

        logger.info("notion_page_created", page_id=data.get("id"))
        return data

    async def update_page(
        self,
        page_id: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Update page properties.

        Args:
            page_id: Page ID
            properties: Properties to update

        Returns:
            Updated page object
        """
        data = await self._request(
            "PATCH",
            f"pages/{page_id}",
            json={"properties": properties},
        )

        logger.info("notion_page_updated", page_id=page_id)
        return data

    async def search(
        self,
        query: str | None = None,
        filter: dict[str, Any] | None = None,
        sort: dict[str, Any] | None = None,
        page_size: int = 100,
        start_cursor: str | None = None,
    ) -> dict[str, Any]:
        """
        Search Notion workspace.

        Args:
            query: Search query
            filter: Filter by object type (page or database)
            sort: Sort configuration
            page_size: Results per page (max 100)
            start_cursor: Pagination cursor

        Returns:
            Dict with 'results' list and pagination info
        """
        body: dict[str, Any] = {
            "page_size": min(page_size, 100),
        }
        if query:
            body["query"] = query
        if filter:
            body["filter"] = filter
        if sort:
            body["sort"] = sort
        if start_cursor:
            body["start_cursor"] = start_cursor

        data = await self._request("POST", "search", json=body)

        return {
            "results": data.get("results", []),
            "has_more": data.get("has_more", False),
            "next_cursor": data.get("next_cursor"),
        }

    async def get_block_children(
        self,
        block_id: str,
        page_size: int = 100,
        start_cursor: str | None = None,
    ) -> dict[str, Any]:
        """
        Get children blocks of a block/page.

        Args:
            block_id: Block or page ID
            page_size: Results per page (max 100)
            start_cursor: Pagination cursor

        Returns:
            Dict with 'results' list and pagination info
        """
        params: dict[str, Any] = {
            "page_size": min(page_size, 100),
        }
        if start_cursor:
            params["start_cursor"] = start_cursor

        data = await self._request(
            "GET",
            f"blocks/{block_id}/children",
            params=params,
        )

        return {
            "results": data.get("results", []),
            "has_more": data.get("has_more", False),
            "next_cursor": data.get("next_cursor"),
        }

    def parse_deal_properties(self, page: dict[str, Any]) -> dict[str, Any]:
        """
        Parse Notion page properties into deal data.

        Args:
            page: Notion page object

        Returns:
            Parsed deal data
        """
        props = page.get("properties", {})

        return {
            "id": page["id"],
            "company_name": self._get_title(props.get("Name", {})),
            "contact_name": self._get_text(props.get("Contact", {})),
            "contact_email": self._get_email(props.get("Email", {})),
            "deal_value": self._get_number(props.get("Value", {})),
            "stage": self._get_select(props.get("Stage", {})),
            "close_date": self._get_date(props.get("Close Date", {})),
            "notes": self._get_text(props.get("Notes", {})),
            "created_time": page.get("created_time"),
            "last_edited_time": page.get("last_edited_time"),
        }

    def _get_title(self, prop: dict[str, Any]) -> str:
        """Extract title property."""
        titles = prop.get("title", [])
        return titles[0]["plain_text"] if titles else ""

    def _get_text(self, prop: dict[str, Any]) -> str:
        """Extract rich_text property."""
        texts = prop.get("rich_text", [])
        return "".join(t["plain_text"] for t in texts) if texts else ""

    def _get_email(self, prop: dict[str, Any]) -> str:
        """Extract email property."""
        return prop.get("email", "") or ""

    def _get_number(self, prop: dict[str, Any]) -> float | None:
        """Extract number property."""
        return prop.get("number")

    def _get_select(self, prop: dict[str, Any]) -> str:
        """Extract select property."""
        select = prop.get("select")
        return select.get("name", "") if select else ""

    def _get_multi_select(self, prop: dict[str, Any]) -> list[str]:
        """Extract multi_select property."""
        return [s.get("name", "") for s in prop.get("multi_select", [])]

    def _get_date(self, prop: dict[str, Any]) -> str | None:
        """Extract date property start value."""
        date = prop.get("date")
        return date.get("start") if date else None

    def _get_checkbox(self, prop: dict[str, Any]) -> bool:
        """Extract checkbox property."""
        return prop.get("checkbox", False)

    async def cleanup(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


class NotionAPIError(Exception):
    """Notion API error."""

    def __init__(
        self,
        message: str,
        code: str | None = None,
        status_code: int | None = None,
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(f"Notion API error: {message} (code={code})")

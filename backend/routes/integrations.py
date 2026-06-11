"""
OAuth Integration Routes
Handles OAuth authorization and callback flows.
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from config import get_settings, Settings
from core.logging import get_logger
from core.types import IntegrationType
from middleware.auth import FirebaseUser, get_current_user, require_workspace_access
from integrations import create_provider_registry
from integrations.oauth.service import OAuthService
from integrations.oauth.token_manager import TokenManager
from integrations.oauth.state_manager import StateManager
from integrations.oauth.errors import OAuthError, OAuthStateError

logger = get_logger("integrations_routes")

router = APIRouter(prefix="/integrations", tags=["integrations"])


# =============================================================================
# Helper Functions
# =============================================================================


def get_frontend_origin(config: Settings) -> str:
    """Get frontend origin from APP_BASE_URL, falling back to dev localhost."""
    if config.app_base_url:
        return config.app_base_url.rstrip("/")
    return "http://localhost:3000"


def validate_provider(provider: str) -> IntegrationType:
    """Validate and convert provider string to IntegrationType."""
    try:
        return IntegrationType(provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")


def sanitize_integration_config(config: dict | None) -> dict:
    """Remove sensitive fields from integration config for API responses."""
    if not config:
        return {}
    # Remove internal fields that shouldn't be exposed
    sensitive_fields = {"scope"}
    return {k: v for k, v in config.items() if k not in sensitive_fields}


def get_oauth_service(
    config: Settings = Depends(get_settings),
):
    """
    Dependency to get OAuthService with all providers.
    Uses DataConnect or asyncpg based on configuration.
    """
    token_manager = TokenManager()

    if config.use_dataconnect:
        from db.dataconnect_client import get_dataconnect_client
        from integrations.oauth.state_manager_dc import StateManagerDC
        from integrations.oauth.service_dc import OAuthServiceDC

        dc = get_dataconnect_client()
        state_manager = StateManagerDC(dc)
        providers = create_provider_registry(dc, config, state_manager)
        return OAuthServiceDC(dc, config, token_manager, state_manager, providers)
    else:
        from db.client import get_db_client

        db = get_db_client()
        state_manager = StateManager(db)
        providers = create_provider_registry(db, config, state_manager)
        return OAuthService(db, config, token_manager, state_manager, providers)


class IntegrationStatusResponse(BaseModel):
    """Integration status response."""

    integration_type: str
    status: str
    connected: bool
    last_sync_at: str | None = None
    last_error: str | None = None
    config: dict | None = None


class IntegrationsListResponse(BaseModel):
    """List of integrations response."""

    integrations: list[IntegrationStatusResponse]


class OAuthStartResponse(BaseModel):
    """OAuth start response."""

    authorization_url: str
    state: str


# =============================================================================
# OAuth Flow Endpoints
# =============================================================================


@router.get("/{provider}/auth")
async def start_oauth(
    provider: str,
    workspace_id: Annotated[str, Query(description="Workspace ID to connect integration to")],
    user: FirebaseUser = Depends(get_current_user),
    oauth_service: OAuthService = Depends(get_oauth_service),
    config: Settings = Depends(get_settings),
):
    """
    Start OAuth authorization flow.

    Redirects user to provider's authorization page.

    Query params:
        - workspace_id: Workspace to connect the integration to

    Returns:
        Redirect to provider's OAuth page
    """
    integration_type = validate_provider(provider)
    frontend_origin = get_frontend_origin(config)
    callback_uri = f"{frontend_origin}/integrations/{provider}/callback"

    try:
        auth_url = await oauth_service.start_oauth_flow(
            workspace_id=workspace_id,
            user_id=user.uid,
            integration_type=integration_type,
            redirect_uri=callback_uri,
        )

        logger.info(
            "oauth_redirect",
            provider=provider,
            workspace_id=workspace_id,
            user_id=user.uid,
        )

        # Redirect to provider's authorization page
        return RedirectResponse(url=auth_url.url, status_code=302)

    except Exception as e:
        logger.error("oauth_start_failed", provider=provider, error=str(e))
        frontend_origin = get_frontend_origin(config)
        return RedirectResponse(
            url=f"{frontend_origin}/app/settings/account?error=oauth_start_failed&provider={provider}",
            status_code=302,
        )


@router.get("/{provider}/auth/url")
async def get_oauth_url(
    provider: str,
    workspace_id: Annotated[str, Query(description="Workspace ID to connect integration to")],
    user: FirebaseUser = Depends(get_current_user),
    oauth_service: OAuthService = Depends(get_oauth_service),
    config: Settings = Depends(get_settings),
) -> OAuthStartResponse:
    """
    Get OAuth authorization URL without redirecting.

    Useful for frontend-controlled OAuth flows (popup windows, etc.)

    Query params:
        - workspace_id: Workspace to connect the integration to

    Returns:
        JSON with authorization_url and state
    """
    integration_type = validate_provider(provider)
    frontend_origin = get_frontend_origin(config)
    callback_uri = f"{frontend_origin}/integrations/{provider}/callback"

    try:
        auth_url = await oauth_service.start_oauth_flow(
            workspace_id=workspace_id,
            user_id=user.uid,
            integration_type=integration_type,
            redirect_uri=callback_uri,
        )

        return OAuthStartResponse(
            authorization_url=auth_url.url,
            state=auth_url.state,
        )

    except Exception as e:
        logger.error("oauth_url_failed", provider=provider, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to generate OAuth URL: {e}")


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: Annotated[str, Query(description="Authorization code from provider")],
    state: Annotated[str, Query(description="State parameter for CSRF protection")],
    oauth_service: OAuthService = Depends(get_oauth_service),
    config: Settings = Depends(get_settings),
):
    """
    OAuth callback endpoint.

    Provider redirects here after user authorizes.
    This endpoint exchanges code for token and redirects to frontend.

    Query params:
        - code: Authorization code
        - state: State parameter (for CSRF protection)

    Returns:
        Redirect to frontend with success or error
    """
    frontend_origin = get_frontend_origin(config)
    callback_uri = f"{frontend_origin}/integrations/{provider}/callback"

    try:
        # Complete OAuth flow
        result = await oauth_service.complete_oauth_flow(
            code=code,
            state=state,
            redirect_uri=callback_uri,
        )

        logger.info(
            "oauth_callback_success",
            provider=provider,
            workspace_id=result["workspace_id"],
        )

        # Redirect to frontend success page
        return RedirectResponse(
            url=f"{frontend_origin}/app/settings/account?success=true&provider={provider}",
            status_code=302,
        )

    except OAuthStateError as e:
        logger.error("oauth_callback_state_error", provider=provider, error=str(e))
        # Redirect to frontend with specific error
        return RedirectResponse(
            url=f"{frontend_origin}/app/settings/account?error=invalid_state&provider={provider}",
            status_code=302,
        )
    except OAuthError as e:
        logger.error("oauth_callback_failed", provider=provider, error=str(e))
        # Redirect to frontend with specific error
        return RedirectResponse(
            url=f"{frontend_origin}/app/settings/account?error={e.code}&provider={provider}",
            status_code=302,
        )
    except Exception as e:
        logger.exception("oauth_callback_error", provider=provider, error=str(e))
        # Redirect to frontend with generic error
        return RedirectResponse(
            url=f"{frontend_origin}/app/settings/account?error=oauth_failed&provider={provider}",
            status_code=302,
        )


# =============================================================================
# Integration Management Endpoints
# =============================================================================


@router.get("")
async def list_integrations(
    workspace_id: Annotated[str, Query(description="Workspace ID")],
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
    oauth_service: OAuthService = Depends(get_oauth_service),
) -> IntegrationsListResponse:
    """
    List all integrations for a workspace.

    Returns integration status without exposing tokens.
    """
    integrations = await oauth_service.list_integrations(workspace_id)

    return IntegrationsListResponse(
        integrations=[
            IntegrationStatusResponse(
                integration_type=i["integration_type"],
                status=i["status"],
                connected=i["status"] == "active",
                last_sync_at=i["last_sync_at"].isoformat() if i.get("last_sync_at") else None,
                last_error=i.get("last_error"),
                config=sanitize_integration_config(i.get("config")),
            )
            for i in integrations
        ]
    )


@router.delete("/{provider}")
async def disconnect_integration(
    provider: str,
    workspace_id: Annotated[str, Query(description="Workspace ID")],
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
    oauth_service: OAuthService = Depends(get_oauth_service),
):
    """
    Disconnect/revoke an OAuth integration.

    Revokes tokens with provider and marks integration as revoked.
    """
    integration_type = validate_provider(provider)

    try:
        await oauth_service.revoke_integration(
            workspace_id=workspace_id,
            integration_type=integration_type,
        )

        logger.info(
            "integration_disconnected",
            provider=provider,
            workspace_id=workspace_id,
            user_id=user.uid,
        )

        return {"success": True, "message": f"{provider} integration disconnected"}

    except Exception as e:
        logger.error("disconnect_failed", provider=provider, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to disconnect integration: {e}")


class NotionDatabase(BaseModel):
    """Notion database summary."""

    id: str
    name: str
    icon: str | None = None
    url: str | None = None


class NotionDatabasesResponse(BaseModel):
    """Response with list of Notion databases."""

    databases: list[NotionDatabase]


@router.get("/notion/databases")
async def list_notion_databases(
    workspace_id: Annotated[str, Query(description="Workspace ID")],
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> NotionDatabasesResponse:
    """
    List Notion databases the user has shared with the integration.

    Returns databases that can be used for importing customers.
    """
    from services import get_integration_service
    from integrations.clients.notion_client import NotionClient, NotionAPIError

    try:
        integration_service = get_integration_service(workspace_id)
        notion_client = NotionClient(integration_service)

        # Search for all databases shared with the integration
        result = await notion_client.search(
            filter={"property": "object", "value": "database"},
            page_size=50,
        )

        databases = []
        for item in result.get("results", []):
            # Extract database name from title
            title_prop = item.get("title", [])
            name = title_prop[0]["plain_text"] if title_prop else "Untitled"

            # Extract icon
            icon = None
            icon_data = item.get("icon")
            if icon_data:
                if icon_data.get("type") == "emoji":
                    icon = icon_data.get("emoji")
                elif icon_data.get("type") == "external":
                    icon = icon_data.get("external", {}).get("url")

            databases.append(
                NotionDatabase(
                    id=item["id"],
                    name=name,
                    icon=icon,
                    url=item.get("url"),
                )
            )

        await notion_client.cleanup()

        return NotionDatabasesResponse(databases=databases)

    except NotionAPIError as e:
        logger.error("notion_databases_error", error=str(e), status=e.status_code)
        raise HTTPException(status_code=e.status_code or 500, detail=e.message)
    except Exception as e:
        logger.error("notion_databases_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list databases: {e}")


@router.get("/{provider}/status")
async def get_integration_status(
    provider: str,
    workspace_id: Annotated[str, Query(description="Workspace ID")],
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> IntegrationStatusResponse:
    """
    Get status of a specific integration.
    """
    from services import get_integration_service

    integration_type = validate_provider(provider)
    integration_service = get_integration_service(workspace_id)
    integration = await integration_service.get_integration(provider)

    if not integration:
        return IntegrationStatusResponse(
            integration_type=provider,
            status="not_connected",
            connected=False,
        )

    last_sync_at = integration.get("last_sync_at")
    if last_sync_at and hasattr(last_sync_at, 'isoformat'):
        last_sync_at = last_sync_at.isoformat()

    return IntegrationStatusResponse(
        integration_type=integration["integration_type"],
        status=integration["status"],
        connected=integration["status"] == "active",
        last_sync_at=last_sync_at,
        last_error=integration.get("last_error"),
        config=sanitize_integration_config(integration.get("config")),
    )


# =============================================================================
# Notion Import Endpoints
# =============================================================================


class NotionProperty(BaseModel):
    """Notion database property/column."""

    id: str
    name: str
    type: str  # title, rich_text, number, select, multi_select, date, email, url, etc.
    options: list[str] | None = None  # For select/multi_select types


class NotionDatabaseSchemaResponse(BaseModel):
    """Response with database schema (properties)."""

    database_id: str
    name: str
    properties: list[NotionProperty]


@router.get("/notion/databases/{database_id}/schema")
async def get_notion_database_schema(
    database_id: str,
    workspace_id: Annotated[str, Query(description="Workspace ID")],
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> NotionDatabaseSchemaResponse:
    """
    Get the schema (properties/columns) of a Notion database.

    Returns property names and types for field mapping UI.
    """
    from services import get_integration_service
    from integrations.clients.notion_client import NotionClient, NotionAPIError

    try:
        integration_service = get_integration_service(workspace_id)
        notion_client = NotionClient(integration_service)

        database = await notion_client.get_database(database_id)

        # Extract database name
        title_prop = database.get("title", [])
        name = title_prop[0]["plain_text"] if title_prop else "Untitled"

        # Parse properties
        properties = []
        for prop_name, prop_data in database.get("properties", {}).items():
            prop_type = prop_data.get("type", "unknown")

            # Extract options for select/multi_select/status/checkbox
            options = None
            if prop_type == "select":
                options = [opt["name"] for opt in prop_data.get("select", {}).get("options", [])]
            elif prop_type == "multi_select":
                options = [opt["name"] for opt in prop_data.get("multi_select", {}).get("options", [])]
            elif prop_type == "status":
                # Notion status has groups (To-do, In progress, Complete) with options inside
                status_data = prop_data.get("status", {})
                options = []
                for group in status_data.get("groups", []):
                    for opt in group.get("option_ids", []):
                        # Find the option by ID
                        for status_opt in status_data.get("options", []):
                            if status_opt.get("id") == opt:
                                options.append(status_opt.get("name"))
                # Fallback: just get all options directly
                if not options:
                    options = [opt["name"] for opt in status_data.get("options", [])]
            elif prop_type == "checkbox":
                # Checkbox fields have two options: checked or unchecked
                options = ["Yes", "No"]

            properties.append(
                NotionProperty(
                    id=prop_data.get("id", prop_name),
                    name=prop_name,
                    type=prop_type,
                    options=options,
                )
            )

        await notion_client.cleanup()

        return NotionDatabaseSchemaResponse(
            database_id=database_id,
            name=name,
            properties=properties,
        )

    except NotionAPIError as e:
        logger.error("notion_schema_error", database_id=database_id, error=str(e))
        raise HTTPException(status_code=e.status_code or 500, detail=e.message)
    except Exception as e:
        logger.error("notion_schema_error", database_id=database_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get database schema: {e}")


class NotionRowPreview(BaseModel):
    """Preview of a Notion database row."""

    id: str
    properties: dict[str, str | float | list[str] | None]  # Parsed property values


class NotionRowsPreviewResponse(BaseModel):
    """Response with preview of database rows."""

    database_id: str
    rows: list[NotionRowPreview]
    total_count: int
    has_more: bool


@router.get("/notion/databases/{database_id}/rows")
async def get_notion_database_rows(
    database_id: str,
    workspace_id: Annotated[str, Query(description="Workspace ID")],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> NotionRowsPreviewResponse:
    """
    Get preview of rows from a Notion database.

    Returns parsed property values for preview before import.
    """
    from services import get_integration_service
    from integrations.clients.notion_client import NotionClient, NotionAPIError

    try:
        integration_service = get_integration_service(workspace_id)
        notion_client = NotionClient(integration_service)

        result = await notion_client.query_database(database_id, page_size=limit)

        rows = []
        for page in result.get("results", []):
            props = page.get("properties", {})
            parsed_props = {}

            for prop_name, prop_data in props.items():
                parsed_props[prop_name] = _parse_notion_property(prop_data, notion_client)

            rows.append(
                NotionRowPreview(
                    id=page["id"],
                    properties=parsed_props,
                )
            )

        await notion_client.cleanup()

        return NotionRowsPreviewResponse(
            database_id=database_id,
            rows=rows,
            total_count=len(rows),
            has_more=result.get("has_more", False),
        )

    except NotionAPIError as e:
        logger.error("notion_rows_error", database_id=database_id, error=str(e))
        raise HTTPException(status_code=e.status_code or 500, detail=e.message)
    except Exception as e:
        logger.error("notion_rows_error", database_id=database_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get database rows: {e}")


def _parse_notion_property(prop_data: dict, notion_client) -> str | float | list[str] | None:
    """Parse a Notion property value to a simple type."""
    prop_type = prop_data.get("type", "")

    if prop_type == "title":
        return notion_client._get_title(prop_data)
    elif prop_type == "rich_text":
        return notion_client._get_text(prop_data)
    elif prop_type == "number":
        return notion_client._get_number(prop_data)
    elif prop_type == "select":
        return notion_client._get_select(prop_data)
    elif prop_type == "multi_select":
        return notion_client._get_multi_select(prop_data)
    elif prop_type == "status":
        # Status is similar to select but nested under "status" key
        status = prop_data.get("status")
        return status.get("name") if status else None
    elif prop_type == "date":
        return notion_client._get_date(prop_data)
    elif prop_type == "email":
        return notion_client._get_email(prop_data)
    elif prop_type == "checkbox":
        return "Yes" if notion_client._get_checkbox(prop_data) else "No"
    elif prop_type == "url":
        return prop_data.get("url", "")
    elif prop_type == "phone_number":
        return prop_data.get("phone_number", "")
    elif prop_type == "status":
        status = prop_data.get("status")
        return status.get("name", "") if status else ""
    else:
        return None


def _extract_all_text_content(props: dict, notion_client, mapped_props: set[str]) -> str:
    """
    Extract ALL text content from Notion properties for enrichment.

    Automatically pulls from any rich_text property that isn't already
    mapped to a structured field. This captures notes, descriptions,
    comments, and any other freeform text.

    Args:
        props: Notion properties dict
        notion_client: NotionClient instance for parsing
        mapped_props: Set of property names already mapped to structured fields

    Returns:
        Combined text from all text properties, with labels
    """
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


def _extract_body_text_for_import(blocks: dict) -> str:
    """
    Extract plain text from Notion page body blocks for raw notes.

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

    return "\n".join(texts)


class FieldMapping(BaseModel):
    """Mapping from Notion property to Herofy field."""

    notion_property: str  # Notion property name
    herofy_field: str  # Herofy customer field


class NotionImportRequest(BaseModel):
    """Request to import customers from Notion."""

    database_id: str
    field_mappings: list[FieldMapping]
    status_field: str | None = None  # Notion property to filter by (e.g., "Stage", "Active")
    import_status_values: list[str] = []  # Only import records with these values (empty = import all)
    skip_enrichment: bool = False  # Skip AI enrichment (for setup flow, enrich at handoff stage)


class ImportedCustomer(BaseModel):
    """Summary of an imported customer."""

    id: str
    name: str
    tier: str | None = None
    lifecycle: str | None = None


class NotionImportResponse(BaseModel):
    """Response after importing customers."""

    imported_count: int
    skipped_count: int = 0  # Records skipped due to status filter
    customers: list[ImportedCustomer]
    errors: list[str] = []


@router.post("/notion/import")
async def import_customers_from_notion(
    request: NotionImportRequest,
    workspace_id: Annotated[str, Query(description="Workspace ID")],
    background_tasks: BackgroundTasks,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> NotionImportResponse:
    """
    Import customers from a Notion database.

    Uses field mappings to transform Notion rows into Herofy customers.

    TODO: Support extracting content from Notion page blocks (not just properties).
    Currently we only read database properties (structured columns). But users often
    have freeform content in the page body (e.g., an "About" section with headings
    and paragraphs). To support this:
    1. Add option to extract page body text (call get_block_children per page)
    2. Look for common heading patterns ("About", "Description", "Notes")
    3. Concatenate block text and map to oneLiner or a notes field
    Note: This adds N+1 API calls which could be slow for large imports.
    See: NotionClient.get_block_children()
    """
    from services import get_integration_service
    from integrations.clients.notion_client import NotionClient, NotionAPIError
    from db.dataconnect_client import get_dataconnect_client
    from config import get_settings
    import re

    settings = get_settings()

    try:
        integration_service = get_integration_service(workspace_id)
        notion_client = NotionClient(integration_service)

        # Build mapping dict for easier lookup
        mapping = {m.notion_property: m.herofy_field for m in request.field_mappings}

        # Log field mappings for debugging
        logger.info(
            "notion_import_field_mappings",
            workspace_id=workspace_id,
            database_id=request.database_id,
            mappings=mapping,
            has_lifecycle="lifecycle" in mapping.values(),
        )

        # Save field mappings and config to integration for future syncs
        await _save_notion_import_config(
            integration_service=integration_service,
            database_id=request.database_id,
            field_mappings=mapping,
            status_field=request.status_field,
        )

        # Fetch all rows from the database (paginate if needed)
        all_rows = []
        cursor = None
        while True:
            result = await notion_client.query_database(
                request.database_id,
                page_size=100,
                start_cursor=cursor,
            )
            all_rows.extend(result.get("results", []))
            if not result.get("has_more"):
                break
            cursor = result.get("next_cursor")

        logger.info("notion_import_fetched", count=len(all_rows), database_id=request.database_id)

        # Get DataConnect client for creating customers
        dc = get_dataconnect_client()

        imported = []
        errors = []

        skipped_by_status = 0

        for row in all_rows:
            try:
                props = row.get("properties", {})
                page_id = row.get("id")

                # Check status field for filtering
                customer_status = None
                if request.status_field and request.status_field in props:
                    customer_status = _parse_notion_property(props[request.status_field], notion_client)
                    customer_status = str(customer_status).strip() if customer_status else None

                # Filter by import_status_values if specified
                if request.import_status_values and len(request.import_status_values) > 0:
                    if not customer_status or customer_status not in request.import_status_values:
                        skipped_by_status += 1
                        continue  # Skip this record

                # Build set of properties that are mapped to structured fields
                # (these won't be included in raw notes extraction)
                mapped_props = set(mapping.keys())

                # Extract ALL text content from properties (notes, descriptions, comments, etc.)
                property_text = _extract_all_text_content(props, notion_client, mapped_props)

                # Also extract page body text (content inside the page)
                body_text = ""
                try:
                    blocks = await notion_client.get_block_children(page_id)
                    body_text = _extract_body_text_for_import(blocks)
                except Exception as e:
                    logger.warning("notion_body_extract_failed", page_id=page_id, error=str(e))

                # Combine all text content for AI enrichment
                raw_notes_parts = []
                if property_text:
                    raw_notes_parts.append(property_text)
                if body_text:
                    raw_notes_parts.append("**Page Content:**\n" + body_text)
                raw_notes = "\n\n---\n\n".join(raw_notes_parts) if raw_notes_parts else None

                # Import as active customer - onboarding setup happens separately
                customer_data = {
                    "workspaceId": workspace_id,
                    "lifecycle": "active",  # Default to active; onboarding setup is separate
                    "rawNotes": raw_notes,
                    "enrichmentStatus": "pending",  # Mark for AI enrichment
                    "externalSource": "notion",  # Track source for syncing
                    "externalId": page_id,  # Track Notion page ID
                }

                # Apply field mappings for structured data only
                for notion_prop, herofy_field in mapping.items():
                    if notion_prop in props:
                        value = _parse_notion_property(props[notion_prop], notion_client)
                        if value is not None and value != "":
                            # Map to correct field name (matching DataConnect schema)
                            if herofy_field == "name":
                                customer_data["name"] = str(value)
                            elif herofy_field == "oneLiner":
                                customer_data["oneLiner"] = str(value)
                            elif herofy_field == "tier":
                                customer_data["tier"] = str(value)
                            elif herofy_field == "arr":
                                # Convert to cents for arrCents field
                                try:
                                    arr_dollars = float(value) if value else 0
                                    customer_data["arrCents"] = int(arr_dollars * 100)
                                except (ValueError, TypeError):
                                    pass
                            elif herofy_field == "lifecycle":
                                # Map to valid CustomerLifecycle enum value
                                # Includes common variations and aliases
                                logger.info(
                                    "lifecycle_mapping_attempt",
                                    notion_prop=notion_prop,
                                    raw_value=value,
                                )
                                lifecycle_map = {
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
                                val = str(value).lower().strip()
                                mapped = lifecycle_map.get(val)
                                if mapped:
                                    customer_data["lifecycle"] = mapped
                                    logger.info(
                                        "lifecycle_mapped",
                                        raw_value=val,
                                        mapped_value=mapped,
                                        customer_name=customer_data.get("name"),
                                    )
                                else:
                                    # Log unmapped values for debugging
                                    logger.warning(
                                        "unmapped_lifecycle_value",
                                        value=val,
                                        customer_name=customer_data.get("name"),
                                    )
                                    # Keep default "active" from line 893

                # Require at least a name
                if not customer_data.get("name"):
                    errors.append(f"Row {row['id'][:8]}: Missing name")
                    continue

                # Generate slug from name
                slug = re.sub(r'[^a-z0-9]+', '-', customer_data["name"].lower()).strip('-')
                customer_data["slug"] = slug

                # Check if customer already exists (by externalId)
                existing_customer = None
                try:
                    existing_result = await dc.execute_query(
                        "GetCustomerByExternalId",
                        {"workspaceId": workspace_id, "externalId": page_id},
                    )
                    existing_customer = existing_result.get("customers", [None])[0] if existing_result.get("customers") else None
                except Exception:
                    pass  # Query might not exist yet, treat as no existing customer

                # Extract stakeholder data before creating customer
                stakeholder_data = {}
                for notion_prop, herofy_field in mapping.items():
                    if notion_prop in props:
                        value = _parse_notion_property(props[notion_prop], notion_client)
                        if value is not None and value != "":
                            if herofy_field == "stakeholderName":
                                stakeholder_data["name"] = str(value)
                            elif herofy_field == "stakeholderEmail":
                                stakeholder_data["email"] = str(value)
                            elif herofy_field == "stakeholderRole":
                                stakeholder_data["role"] = str(value)

                # Create or update customer via DataConnect
                if existing_customer:
                    # Update existing customer
                    customer_id = existing_customer["id"]
                    update_data = {
                        "id": customer_id,
                        "lifecycle": customer_data.get("lifecycle"),
                        "rawNotes": customer_data.get("rawNotes"),
                        "enrichmentStatus": "pending",
                    }
                    # Also update name/tier if they changed
                    if customer_data.get("name"):
                        update_data["name"] = customer_data["name"]
                    if customer_data.get("tier"):
                        update_data["tier"] = customer_data["tier"]
                    if customer_data.get("arrCents"):
                        update_data["arrCents"] = str(customer_data["arrCents"])

                    await dc.execute_mutation("UpdateCustomer", update_data)
                    logger.info(
                        "notion_import_updated_existing",
                        customer_id=customer_id,
                        name=customer_data.get("name"),
                        lifecycle=customer_data.get("lifecycle"),
                    )
                else:
                    # Create new customer
                    result = await dc.execute_mutation("CreateCustomer", customer_data)
                    customer_id = result.get("customer_insert", {}).get("id", row["id"])

                # Create stakeholder if we have at least a name
                if stakeholder_data.get("name"):
                    try:
                        await dc.execute_mutation("CreateStakeholder", {
                            "workspaceId": workspace_id,
                            "customerId": customer_id,
                            "name": stakeholder_data["name"],
                            "email": stakeholder_data.get("email"),
                            "role": stakeholder_data.get("role", "Primary Contact"),
                        })
                        logger.debug(
                            "stakeholder_created",
                            customer_id=customer_id,
                            stakeholder_name=stakeholder_data["name"],
                        )
                    except Exception as e:
                        logger.warning(
                            "stakeholder_create_failed",
                            customer_id=customer_id,
                            error=str(e),
                        )

                imported.append(
                    ImportedCustomer(
                        id=customer_id,
                        name=customer_data["name"],
                        tier=customer_data.get("tier"),
                        lifecycle=customer_data.get("lifecycle"),
                    )
                )

            except Exception as e:
                errors.append(f"Row {row['id'][:8]}: {str(e)}")
                logger.warning("notion_import_row_error", row_id=row["id"], error=str(e))

        await notion_client.cleanup()

        logger.info(
            "notion_import_completed",
            total_rows=len(all_rows),
            imported=len(imported),
            skipped_by_status=skipped_by_status,
            errors=len(errors),
            workspace_id=workspace_id,
        )

        # Trigger background enrichment for imported customers (unless skipped for setup flow)
        if imported and not request.skip_enrichment:
            from services.enrichment_service import process_enrichment_queue
            background_tasks.add_task(process_enrichment_queue, workspace_id)
            logger.info(
                "enrichment_triggered",
                workspace_id=workspace_id,
                customers_to_enrich=len(imported),
            )
        elif imported and request.skip_enrichment:
            logger.info(
                "enrichment_skipped_for_setup",
                workspace_id=workspace_id,
                customers_imported=len(imported),
            )

        return NotionImportResponse(
            imported_count=len(imported),
            skipped_count=skipped_by_status,
            customers=imported,
            errors=errors[:10],  # Limit errors to first 10
        )

    except NotionAPIError as e:
        logger.error("notion_import_error", error=str(e))
        raise HTTPException(status_code=e.status_code or 500, detail=e.message)
    except Exception as e:
        logger.error("notion_import_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to import customers: {e}")


async def _save_notion_import_config(
    integration_service,
    database_id: str,
    field_mappings: dict[str, str],
    status_field: str | None,
) -> None:
    """
    Save Notion import configuration for future syncs.

    Stores the database ID, field mappings, and status field config
    in the integration config so syncs know how to interpret Notion data.
    """
    from core.types import IntegrationType
    import json

    try:
        integration = await integration_service.get_integration(IntegrationType.NOTION)
        if not integration:
            logger.warning("notion_integration_not_found", msg="Cannot save config")
            return

        # Merge with existing config
        existing_config = integration.get("config", {})
        if isinstance(existing_config, str):
            existing_config = json.loads(existing_config) if existing_config else {}

        existing_config["database_id"] = database_id
        existing_config["field_mappings"] = field_mappings
        if status_field:
            existing_config["status_field"] = status_field

        # Save updated config
        await integration_service.update_config(
            IntegrationType.NOTION,
            existing_config,
            merge=False,  # Replace entire config with our updated version
        )

        logger.info(
            "notion_config_saved",
            database_id=database_id,
            mappings_count=len(field_mappings),
            status_field=status_field,
        )

    except Exception as e:
        logger.warning("notion_config_save_failed", error=str(e))


# =============================================================================
# Notion Poll Configuration
# =============================================================================


class NotionPollConfigRequest(BaseModel):
    """Request to configure Notion polling settings."""

    status_field: str  # Notion property to filter by (e.g., "Lifecycle", "Stage")
    closed_value: str  # Value that indicates a closed/won deal (e.g., "Onboarding", "Won")


class NotionPollConfigResponse(BaseModel):
    """Response after updating poll config."""

    success: bool
    status_field: str
    closed_value: str


@router.post("/notion/poll-config")
async def configure_notion_poll(
    request: NotionPollConfigRequest,
    workspace_id: Annotated[str, Query(description="Workspace ID")],
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> NotionPollConfigResponse:
    """
    Configure Notion polling settings for detecting closed deals.

    Sets which Notion property to filter by and what value indicates a closed deal.
    """
    from services import get_integration_service
    from core.types import IntegrationType
    import json

    integration_service = get_integration_service(workspace_id)

    try:
        integration = await integration_service.get_integration(IntegrationType.NOTION)
        if not integration:
            raise HTTPException(status_code=404, detail="Notion integration not found")

        # Merge with existing config
        existing_config = integration.get("config", {})
        if isinstance(existing_config, str):
            existing_config = json.loads(existing_config) if existing_config else {}

        existing_config["status_field"] = request.status_field
        existing_config["closed_value"] = request.closed_value

        # Save updated config
        await integration_service.update_config(
            IntegrationType.NOTION,
            existing_config,
            merge=False,
        )

        logger.info(
            "notion_poll_config_updated",
            workspace_id=workspace_id,
            status_field=request.status_field,
            closed_value=request.closed_value,
        )

        return NotionPollConfigResponse(
            success=True,
            status_field=request.status_field,
            closed_value=request.closed_value,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("notion_poll_config_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update config: {e}")


# =============================================================================
# Notion Sync Endpoint (Manual Refresh)
# =============================================================================


class SyncResponse(BaseModel):
    """Response after syncing from external source."""

    success: bool
    message: str
    updated_fields: list[str] = []
    source: str | None = None


class SyncAllResponse(BaseModel):
    """Response after syncing all customers."""

    success: bool
    synced_count: int
    skipped_count: int
    error_count: int
    errors: list[str] = []


@router.post("/sync/all")
async def sync_all_customers(
    workspace_id: Annotated[str, Query(description="Workspace ID")],
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> SyncAllResponse:
    """
    Sync all customers from their external sources.

    Iterates through customers with external_source set and refreshes
    their data from the original source (Notion, HubSpot, etc).

    This is vendor-agnostic - it uses the external_source field to
    determine which integration to use for each customer.
    """
    from db.dataconnect_client import get_dataconnect_client

    try:
        dc = get_dataconnect_client()

        # Get all customers with external sources
        result = await dc.execute_query(
            "GetCustomersWithExternalSource",
            {"workspaceId": workspace_id},
        )

        customers = result.get("customers", [])
        synced = 0
        skipped = 0
        errors_list = []

        for customer in customers:
            external_source = customer.get("externalSource")
            external_id = customer.get("externalId")

            if not external_source or not external_id:
                skipped += 1
                continue

            try:
                if external_source == "notion":
                    # Sync from Notion
                    await _sync_customer_from_notion(
                        workspace_id=workspace_id,
                        customer_id=customer["id"],
                        external_id=external_id,
                    )
                    synced += 1
                elif external_source == "hubspot":
                    # TODO: Implement HubSpot sync
                    skipped += 1
                elif external_source == "pipedrive":
                    # TODO: Implement Pipedrive sync
                    skipped += 1
                else:
                    skipped += 1

            except Exception as e:
                errors_list.append(f"{customer.get('name', external_id)}: {str(e)}")

        logger.info(
            "sync_all_completed",
            workspace_id=workspace_id,
            synced=synced,
            skipped=skipped,
            errors=len(errors_list),
        )

        return SyncAllResponse(
            success=True,
            synced_count=synced,
            skipped_count=skipped,
            error_count=len(errors_list),
            errors=errors_list[:10],  # Limit to first 10 errors
        )

    except Exception as e:
        logger.error("sync_all_failed", workspace_id=workspace_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")


async def _sync_customer_from_notion(
    workspace_id: str,
    customer_id: str,
    external_id: str,
) -> dict:
    """
    Sync a single customer from Notion.

    Fetches latest data and ALL text content for re-enrichment.

    Args:
        workspace_id: Workspace ID
        customer_id: Customer ID to update
        external_id: Notion page ID

    Returns:
        Updated field names
    """
    from services import get_integration_service
    from integrations.clients.notion_client import NotionClient
    from db.dataconnect_client import get_dataconnect_client
    from core.types import IntegrationType

    integration_service = get_integration_service(workspace_id)
    notion_client = NotionClient(integration_service)

    try:
        # Fetch page and blocks
        page = await notion_client.get_page(external_id)
        blocks = await notion_client.get_block_children(external_id)
        props = page.get("properties", {})

        # Get the workspace's field mapping config (if any)
        integration = await integration_service.get_integration(IntegrationType.NOTION)
        config = integration.get("config", {}) if integration else {}
        field_mappings = config.get("field_mappings", {})
        mapped_props = set(field_mappings.keys())

        # Extract ALL text content from properties (not mapped to structured fields)
        property_text = _extract_all_text_content(props, notion_client, mapped_props)

        # Extract page body text
        body_text = _extract_body_text_for_import(blocks)

        # Combine all text for enrichment
        raw_notes_parts = []
        if property_text:
            raw_notes_parts.append(property_text)
        if body_text:
            raw_notes_parts.append("**Page Content:**\n" + body_text)
        combined_notes = "\n\n---\n\n".join(raw_notes_parts) if raw_notes_parts else None

        # Extract structured fields
        dc = get_dataconnect_client()
        update_data = {"id": customer_id}

        # Try to get name from title property
        for prop_name, prop_data in props.items():
            if prop_data.get("type") == "title":
                name = notion_client._get_title(prop_data)
                if name:
                    update_data["name"] = name
                break

        # Try to get ARR from number properties
        for prop_name, prop_data in props.items():
            prop_lower = prop_name.lower()
            if prop_data.get("type") == "number" and ("arr" in prop_lower or "revenue" in prop_lower):
                arr = notion_client._get_number(prop_data)
                if arr:
                    update_data["arrCents"] = str(int(arr * 100))
                break

        # Store full notes for AI enrichment and reset enrichment status
        if combined_notes:
            update_data["rawNotes"] = combined_notes
            update_data["enrichmentStatus"] = "pending"  # Trigger re-enrichment

        await dc.execute_mutation("UpdateCustomer", update_data)

        # If we have new notes, trigger enrichment
        if combined_notes:
            from services.enrichment_service import enrich_single_customer
            try:
                await enrich_single_customer(workspace_id, customer_id)
                logger.info("sync_enrichment_triggered", customer_id=customer_id)
            except Exception as e:
                logger.warning("sync_enrichment_failed", customer_id=customer_id, error=str(e))

        return parsed

    finally:
        await notion_client.cleanup()


@router.post("/sync/{page_id}")
async def sync_single_page(
    page_id: str,
    workspace_id: Annotated[str, Query(description="Workspace ID")],
    source: Annotated[str, Query(description="Source type: notion, hubspot, etc.")] = "notion",
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> SyncResponse:
    """
    Sync (refresh) data from a specific external page/record.

    Fetches the latest data from the external source and returns what changed.
    This is a manual refresh endpoint - no polling, user-triggered only.

    Query params:
        - source: The integration type (notion, hubspot, pipedrive)
        - page_id: The external record ID
    """
    if source == "notion":
        return await _sync_notion_page(page_id, workspace_id)
    elif source == "hubspot":
        # TODO: Implement HubSpot sync
        raise HTTPException(status_code=501, detail="HubSpot sync not yet implemented")
    elif source == "pipedrive":
        # TODO: Implement Pipedrive sync
        raise HTTPException(status_code=501, detail="Pipedrive sync not yet implemented")
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported source: {source}")


async def _sync_notion_page(page_id: str, workspace_id: str) -> SyncResponse:
    """Sync a single Notion page and return the result."""
    from services import get_integration_service
    from integrations.clients.notion_client import NotionClient, NotionAPIError
    from tools.notion_tool import _parse_notion_deal_page, DEFAULT_PROPERTY_MAPPING
    from core.types import IntegrationType

    try:
        integration_service = get_integration_service(workspace_id)
        notion_client = NotionClient(integration_service)

        # Fetch page and blocks
        page = await notion_client.get_page(page_id)
        blocks = await notion_client.get_block_children(page_id)

        # Get custom property mapping from workspace config (if set)
        integration = await integration_service.get_integration(IntegrationType.NOTION)
        custom_mapping: dict[str, list[str]] = {}
        if integration:
            config = integration.get("config", {})
            custom_mapping = config.get("property_mapping", {})

        # Merge custom mapping with defaults
        property_mapping = {**DEFAULT_PROPERTY_MAPPING}
        for key, candidates in custom_mapping.items():
            if isinstance(candidates, list):
                property_mapping[key] = candidates

        # Parse the page
        parsed_data = _parse_notion_deal_page(page, blocks, property_mapping)

        await notion_client.cleanup()

        # Log what we found
        updated_fields = [k for k, v in parsed_data.items() if v is not None and v != "" and v != []]

        logger.info(
            "sync_page_completed",
            source="notion",
            page_id=page_id,
            workspace_id=workspace_id,
            fields=updated_fields,
        )

        return SyncResponse(
            success=True,
            message=f"Synced {len(updated_fields)} fields from Notion",
            updated_fields=updated_fields,
            source="notion",
        )

    except NotionAPIError as e:
        logger.error("sync_page_error", source="notion", page_id=page_id, error=str(e))
        raise HTTPException(status_code=e.status_code or 500, detail=e.message)
    except Exception as e:
        logger.error("sync_page_error", source="notion", page_id=page_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to sync from Notion: {e}")


# =============================================================================
# Notion Page Browse & Link Endpoints (Multi-page linking support)
# =============================================================================


class NotionPageResult(BaseModel):
    """A Notion page result from search."""

    id: str
    title: str
    url: str
    icon: str | None = None
    last_edited: str | None = None
    parent_type: str | None = None  # "database" | "page" | "workspace"


class NotionPagesResponse(BaseModel):
    """Response from searching Notion pages."""

    pages: list[NotionPageResult]
    has_more: bool = False
    next_cursor: str | None = None


class NotionPageValidateRequest(BaseModel):
    """Request to validate a Notion link."""

    url: str


class NotionPageValidateResponse(BaseModel):
    """Response from validating a Notion link."""

    valid: bool
    has_access: bool
    page_id: str | None = None
    title: str | None = None
    url: str | None = None
    error: str | None = None


class LinkedPage(BaseModel):
    """A linked external page for a customer."""

    source: str  # "notion", "hubspot", etc.
    id: str
    type: str  # "handoff", "tracker", "notes", "other"
    url: str
    title: str
    content: str | None = None  # Page content for AI processing
    hasAccess: bool = True


class LinkPageRequest(BaseModel):
    """Request to link a page to a customer."""

    source: str
    page_id: str
    page_type: str  # "handoff", "tracker", "notes", "other"
    url: str
    title: str


class LinkPageResponse(BaseModel):
    """Response after linking a page."""

    success: bool
    linked_pages: list[LinkedPage]


@router.get("/notion/pages")
async def search_notion_pages(
    workspace_id: Annotated[str, Query(description="Workspace ID")],
    query: Annotated[str | None, Query(description="Search query")] = None,
    cursor: Annotated[str | None, Query(description="Pagination cursor")] = None,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> NotionPagesResponse:
    """
    Search for Notion pages the user can access.

    Used by the "Browse Notion pages" modal to let users find and link
    pages to customers for handoff docs, trackers, etc.
    """
    from services import get_integration_service
    from integrations.clients.notion_client import NotionClient, NotionAPIError

    try:
        integration_service = get_integration_service(workspace_id)
        notion_client = NotionClient(integration_service)

        # Search for pages only (not databases)
        result = await notion_client.search(
            query=query,
            filter={"property": "object", "value": "page"},
            page_size=20,
            start_cursor=cursor,
        )

        pages = []
        for page in result.get("results", []):
            # Extract title from properties
            title = ""
            props = page.get("properties", {})
            for prop_data in props.values():
                if prop_data.get("type") == "title":
                    title_arr = prop_data.get("title", [])
                    if title_arr:
                        title = "".join(t.get("plain_text", "") for t in title_arr)
                    break

            # Fallback to page ID if no title
            if not title:
                title = f"Untitled ({page['id'][:8]}...)"

            # Get icon
            icon = None
            icon_data = page.get("icon")
            if icon_data:
                if icon_data.get("type") == "emoji":
                    icon = icon_data.get("emoji")
                elif icon_data.get("type") == "external":
                    icon = icon_data.get("external", {}).get("url")

            # Get parent type
            parent = page.get("parent", {})
            parent_type = parent.get("type")  # "database_id", "page_id", "workspace"

            pages.append(
                NotionPageResult(
                    id=page["id"],
                    title=title,
                    url=page.get("url", f"https://notion.so/{page['id'].replace('-', '')}"),
                    icon=icon,
                    last_edited=page.get("last_edited_time"),
                    parent_type=parent_type,
                )
            )

        await notion_client.cleanup()

        return NotionPagesResponse(
            pages=pages,
            has_more=result.get("has_more", False),
            next_cursor=result.get("next_cursor"),
        )

    except NotionAPIError as e:
        logger.error("notion_pages_search_error", error=str(e))
        raise HTTPException(status_code=e.status_code or 500, detail=e.message)
    except Exception as e:
        logger.error("notion_pages_search_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to search Notion: {e}")


@router.post("/notion/pages/validate")
async def validate_notion_link(
    request: NotionPageValidateRequest,
    workspace_id: Annotated[str, Query(description="Workspace ID")],
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> NotionPageValidateResponse:
    """
    Validate a pasted Notion link and check if we have access.

    Parses the URL to extract page ID, then attempts to fetch the page
    to verify access. Returns page metadata if accessible.
    """
    from services import get_integration_service
    from integrations.clients.notion_client import NotionClient, NotionAPIError
    import re

    url = request.url.strip()

    # Parse Notion URL to extract page ID
    # Formats:
    # - https://www.notion.so/workspace/Page-Title-abc123def456
    # - https://notion.so/abc123def456
    # - https://www.notion.so/abc123def456?v=...
    # - notion://notion.so/workspace/Page-Title-abc123def456

    page_id = None

    # Try to extract 32-char hex ID (with or without dashes)
    # Notion IDs are 32 hex chars, sometimes with dashes
    hex_pattern = r"([a-f0-9]{32}|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})"
    match = re.search(hex_pattern, url, re.IGNORECASE)

    if match:
        page_id = match.group(1)
        # Normalize to dashed format
        if "-" not in page_id:
            page_id = f"{page_id[:8]}-{page_id[8:12]}-{page_id[12:16]}-{page_id[16:20]}-{page_id[20:]}"
    else:
        return NotionPageValidateResponse(
            valid=False,
            has_access=False,
            error="Could not parse Notion page ID from URL",
        )

    # Try to fetch the page
    try:
        integration_service = get_integration_service(workspace_id)
        notion_client = NotionClient(integration_service)

        page = await notion_client.get_page(page_id)

        # Extract title
        title = ""
        props = page.get("properties", {})
        for prop_data in props.values():
            if prop_data.get("type") == "title":
                title_arr = prop_data.get("title", [])
                if title_arr:
                    title = "".join(t.get("plain_text", "") for t in title_arr)
                break

        if not title:
            title = f"Untitled ({page_id[:8]}...)"

        await notion_client.cleanup()

        return NotionPageValidateResponse(
            valid=True,
            has_access=True,
            page_id=page_id,
            title=title,
            url=page.get("url", url),
        )

    except NotionAPIError as e:
        logger.warning("notion_validate_no_access", page_id=page_id, error=str(e))
        # Check if it's an access error vs other error
        if e.status_code == 404 or e.status_code == 403:
            return NotionPageValidateResponse(
                valid=True,
                has_access=False,
                page_id=page_id,
                error="Page exists but we don't have access. Share it with the Herofy integration.",
            )
        return NotionPageValidateResponse(
            valid=False,
            has_access=False,
            error=f"Failed to validate: {e.message}",
        )
    except Exception as e:
        logger.error("notion_validate_error", page_id=page_id, error=str(e))
        return NotionPageValidateResponse(
            valid=False,
            has_access=False,
            error=f"Failed to validate link: {str(e)}",
        )


@router.post("/customers/{customer_id}/linked-pages")
async def link_page_to_customer(
    customer_id: str,
    request: LinkPageRequest,
    workspace_id: Annotated[str, Query(description="Workspace ID")],
    background_tasks: BackgroundTasks,
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> LinkPageResponse:
    """
    Link an external page to a customer.

    Adds the page to the customer's linkedPages JSON array.
    Used for handoff docs, onboarding trackers, meeting notes, etc.

    The linkedPages field is vendor-agnostic - supports Notion, HubSpot, etc.
    For Notion pages, we also fetch and store the page content for AI processing,
    then trigger re-enrichment to extract goals, signals, and stakeholders.
    """
    from db.dataconnect_client import get_dataconnect_client
    from services.enrichment_service import process_enrichment_queue
    import json

    try:
        # For Notion pages, use the shared service that handles content extraction
        if request.source == "notion":
            from services.notion_service_dc import link_notion_page_to_customer

            result = await link_notion_page_to_customer(
                workspace_id=workspace_id,
                customer_id=customer_id,
                page_id=request.page_id,
                page_title=request.title,
                page_type=request.page_type or "linked_doc",
                trigger_enrichment=True,
            )

            if not result.get("success"):
                if result.get("error") == "Customer not found":
                    raise HTTPException(status_code=404, detail="Customer not found")
                raise HTTPException(status_code=500, detail=result.get("error", "Failed to link page"))

            # Trigger background enrichment processing
            if result.get("content_length", 0) > 0:
                background_tasks.add_task(process_enrichment_queue, workspace_id)

            # Get updated linked pages for response
            dc = get_dataconnect_client()
            customer_result = await dc.execute_query("GetCustomer", {"id": customer_id})
            customer = customer_result.get("customer")
            linked_pages_json = customer.get("linkedPages") if customer else "[]"
            linked_pages = json.loads(linked_pages_json) if linked_pages_json else []

            return LinkPageResponse(
                success=True,
                linked_pages=[LinkedPage(**p) for p in linked_pages],
            )

        # For non-Notion pages, use simple linking without content extraction
        dc = get_dataconnect_client()

        # Get current customer to read existing linked pages
        result = await dc.execute_query("GetCustomer", {"id": customer_id})
        customer = result.get("customer")

        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

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
            if page.get("source") == request.source and page.get("id") == request.page_id:
                return LinkPageResponse(
                    success=True,
                    linked_pages=[LinkedPage(**p) for p in linked_pages],
                )

        # Add new linked page (no content for non-Notion sources)
        new_page = {
            "source": request.source,
            "id": request.page_id,
            "type": request.page_type,
            "url": request.url,
            "title": request.title,
            "content": None,
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
            source=request.source,
            page_id=request.page_id,
            page_type=request.page_type,
        )

        return LinkPageResponse(
            success=True,
            linked_pages=[LinkedPage(**p) for p in linked_pages],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "link_page_error",
            customer_id=customer_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"Failed to link page: {e}")


@router.delete("/customers/{customer_id}/linked-pages/{page_id}")
async def unlink_page_from_customer(
    customer_id: str,
    page_id: str,
    workspace_id: Annotated[str, Query(description="Workspace ID")],
    user: FirebaseUser = Depends(require_workspace_access("workspace_id")),
) -> LinkPageResponse:
    """
    Unlink a page from a customer.

    Args:
        customer_id: Customer ID
        page_id: The page ID to unlink (can be Notion page ID or title)
        workspace_id: Workspace ID from query params
        user: Authenticated user

    Returns:
        Updated list of linked pages
    """
    logger.info(
        "unlink_page_request",
        customer_id=customer_id,
        page_id=page_id,
        workspace_id=workspace_id,
    )

    try:
        from db.dataconnect_client import get_dataconnect_client

        dc = get_dataconnect_client()

        # Get customer
        customer = await dc.get_customer(customer_id=customer_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        # Parse existing linked pages
        existing_json = customer.get("linkedPages")
        linked_pages: list[dict] = []
        if existing_json:
            try:
                linked_pages = json.loads(existing_json)
            except json.JSONDecodeError:
                linked_pages = []

        # Remove the page (match by page_id or title)
        original_count = len(linked_pages)
        linked_pages = [
            page for page in linked_pages
            if page.get("id") != page_id and page.get("title") != page_id
        ]

        if len(linked_pages) == original_count:
            # Page not found, but that's ok - return current state
            logger.warning(
                "page_not_found_for_unlink",
                customer_id=customer_id,
                page_id=page_id,
            )

        # Save updated linked pages
        await dc.execute_mutation(
            "UpdateCustomerLinkedPages",
            {
                "id": customer_id,
                "linkedPages": json.dumps(linked_pages) if linked_pages else None,
            },
        )

        logger.info(
            "page_unlinked_from_customer",
            customer_id=customer_id,
            page_id=page_id,
            remaining_pages=len(linked_pages),
        )

        return LinkPageResponse(
            success=True,
            linked_pages=[LinkedPage(**p) for p in linked_pages],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "unlink_page_error",
            customer_id=customer_id,
            page_id=page_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"Failed to unlink page: {e}")

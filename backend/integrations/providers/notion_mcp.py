"""
Notion hosted-MCP OAuth provider (mcp.notion.com).

This is a SEPARATE OAuth flow from the Notion REST integration (`notion.py`). The REST
token (api.notion.com/v1/oauth) is rejected by the hosted MCP server — mcp.notion.com runs
its own authorization server and requires OAuth 2.0 Authorization-Code + PKCE with Dynamic
Client Registration (RFC 7591). MCP access tokens are short-lived (~1h) WITH rotating refresh
tokens, so unlike the REST provider this one implements real refresh.

Flow (verified against Notion, June 2026):
  - Discovery: GET https://mcp.notion.com/.well-known/oauth-authorization-server
      → authorization_endpoint=/authorize, token_endpoint=/token, registration_endpoint=/register,
        S256 supported, token_endpoint_auth_method "none" (public client).
  - DCR: POST /register (unauthenticated) → client_id, no secret.
  - Authorize → callback → token exchange (with code_verifier, no client_secret) → access/refresh.

Reference: https://developers.notion.com/guides/mcp/build-mcp-client
"""

from typing import Any
from urllib.parse import urlencode

import httpx
from authlib.common.security import generate_token
from authlib.oauth2.rfc7636 import create_s256_code_challenge

from core.logging import get_logger
from integrations.oauth.protocol import OAuthAuthorizationUrl, OAuthTokenResponse
from integrations.oauth.errors import OAuthExchangeError, OAuthRefreshError
from integrations.providers.base import BaseOAuthProvider

logger = get_logger("NotionMcpOAuthProvider")

NOTION_MCP_BASE = "https://mcp.notion.com"
_AUTH_SERVER_METADATA_URL = f"{NOTION_MCP_BASE}/.well-known/oauth-authorization-server"

# Module-level (process-wide) caches so they survive per-request provider instances.
# Endpoints seed from the verified values; discovery may refresh them (beta server).
_ENDPOINTS: dict[str, str] = {
    "authorization_endpoint": f"{NOTION_MCP_BASE}/authorize",
    "token_endpoint": f"{NOTION_MCP_BASE}/token",
    "registration_endpoint": f"{NOTION_MCP_BASE}/register",
}
_DISCOVERED = False
# Dynamically-registered public clients, keyed by redirect_uri (DCR is per redirect_uri).
_DCR_CLIENTS: dict[str, str] = {}


class NotionMcpOAuthProvider(BaseOAuthProvider):
    """OAuth 2.0 + PKCE + Dynamic Client Registration provider for Notion's hosted MCP server."""

    @property
    def provider_name(self) -> str:
        return "notion_mcp"

    @property
    def authorization_endpoint(self) -> str:
        return _ENDPOINTS["authorization_endpoint"]

    @property
    def token_endpoint(self) -> str:
        return _ENDPOINTS["token_endpoint"]

    @property
    def revocation_endpoint(self) -> str | None:
        # Notion advertises revocation at /token, but it expects client auth we don't have as a
        # public client. Disconnect just drops the local record; skip remote revocation.
        return None

    def get_default_scopes(self) -> list[str]:
        return []

    def get_client_credentials(self) -> tuple[str, str]:
        """Public client: id only, no secret. Pinned id (settings) wins; else best-effort cache."""
        return (self._configured_client_id() or self._any_cached_client_id() or "", "")

    # ── discovery & dynamic client registration ──────────────────────────────

    async def _ensure_discovered(self) -> None:
        global _DISCOVERED
        if _DISCOVERED:
            return
        try:
            resp = await self.http_client.get(
                _AUTH_SERVER_METADATA_URL, headers={"Accept": "application/json"}
            )
            resp.raise_for_status()
            meta = resp.json()
            for key in ("authorization_endpoint", "token_endpoint", "registration_endpoint"):
                if meta.get(key):
                    _ENDPOINTS[key] = meta[key]
        except Exception as e:  # fall back to the verified defaults
            logger.warning("notion_mcp_discovery_failed", error=str(e))
        _DISCOVERED = True

    def _configured_client_id(self) -> str:
        return getattr(self.config, "notion_mcp_client_id", "") or ""

    def _any_cached_client_id(self) -> str | None:
        # Used by refresh (which has no redirect_uri to key on). A single dev redirect_uri is the
        # common case; if there are several, the env-pinned id should be set instead.
        return next(iter(_DCR_CLIENTS.values()), None)

    async def _get_client_id(self, redirect_uri: str) -> str:
        """Resolve the public client_id for `redirect_uri`: pinned env → cache → register (DCR)."""
        pinned = self._configured_client_id()
        if pinned:
            return pinned
        if redirect_uri in _DCR_CLIENTS:
            return _DCR_CLIENTS[redirect_uri]
        client_id = await self._register_client(redirect_uri)
        _DCR_CLIENTS[redirect_uri] = client_id
        return client_id

    async def _register_client(self, redirect_uri: str) -> str:
        payload = {
            "client_name": "Herofy",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        }
        resp = await self.http_client.post(
            _ENDPOINTS["registration_endpoint"], json=payload, headers={"Accept": "application/json"}
        )
        resp.raise_for_status()
        client_id = resp.json()["client_id"]
        logger.warning(
            "notion_mcp_dcr_registered",
            client_id=client_id,
            redirect_uri=redirect_uri,
            hint="Pin NOTION_MCP_CLIENT_ID to this value so refresh survives restarts.",
        )
        return client_id

    # ── authorization-code + PKCE ────────────────────────────────────────────

    async def get_authorization_url(
        self,
        workspace_id: str,
        user_id: str,
        redirect_uri: str,
        scopes: list[str] | None = None,
    ) -> OAuthAuthorizationUrl:
        await self._ensure_discovered()
        client_id = await self._get_client_id(redirect_uri)

        code_verifier = generate_token(48)
        code_challenge = create_s256_code_challenge(code_verifier)

        # Persist the PKCE verifier with the CSRF state for the callback (existing plumbing).
        state = await self.state_manager.create_state(
            workspace_id=workspace_id,
            user_id=user_id,
            integration_type=self._get_integration_type(),
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
        )

        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        url = f"{self.authorization_endpoint}?{urlencode(params)}"
        logger.info("notion_mcp_authorization_url_generated", workspace_id=workspace_id)
        return OAuthAuthorizationUrl(url=url, state=state)

    async def exchange_code(
        self,
        code: str,
        state: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> OAuthTokenResponse:
        await self._ensure_discovered()
        client_id = await self._get_client_id(redirect_uri)
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,  # public client — no client_secret
        }
        if code_verifier:
            data["code_verifier"] = code_verifier
        return await self._post_token(data, OAuthExchangeError)

    async def refresh_access_token(self, refresh_token: str) -> OAuthTokenResponse:
        await self._ensure_discovered()
        client_id = self._configured_client_id() or self._any_cached_client_id()
        if not client_id:
            # No stable client_id available (e.g. process restarted before pinning the env var).
            raise OAuthRefreshError(
                "No Notion MCP client_id available to refresh; set NOTION_MCP_CLIENT_ID.",
                provider=self.provider_name,
            )
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        }
        return await self._post_token(data, OAuthRefreshError)

    async def _post_token(self, data: dict[str, Any], error_cls) -> OAuthTokenResponse:
        try:
            resp = await self.http_client.post(
                self.token_endpoint, data=data, headers={"Accept": "application/json"}
            )
            resp.raise_for_status()
            return self._parse_token_response(resp.json())
        except httpx.HTTPStatusError as e:
            body = e.response.text[:200] if e.response.text else "no body"
            logger.error("notion_mcp_token_failed", status=e.response.status_code, error=body)
            raise error_cls(f"HTTP {e.response.status_code}", provider=self.provider_name)
        except Exception as e:
            logger.error("notion_mcp_token_error", error=str(e))
            raise error_cls(str(e), provider=self.provider_name)

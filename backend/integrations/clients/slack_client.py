"""
Slack API Client
Uses httpx for Slack Web API access.
"""

from typing import Any

import httpx

from core.logging import get_logger
from core.errors import IntegrationAuthError
from services.integration_service_dc import IntegrationServiceDC
from core.types import IntegrationType

logger = get_logger("SlackClient")

# Slack error codes that indicate auth failure
SLACK_AUTH_ERRORS = {
    "invalid_auth",
    "token_revoked",
    "token_expired",
    "not_authed",
    "account_inactive",
    "org_login_required",
}


class SlackClient:
    """
    Slack Web API client.

    Docs: https://api.slack.com/web
    """

    BASE_URL = "https://slack.com/api"

    def __init__(self, integration_service: IntegrationServiceDC):
        """
        Initialize Slack client.

        Args:
            integration_service: Service for getting valid tokens
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
            IntegrationType.SLACK
        )
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs,
    ) -> dict[str, Any]:
        """Make authenticated Slack API request."""
        headers = await self._get_headers()
        url = f"{self.BASE_URL}/{endpoint}"

        response = await self.http_client.request(
            method,
            url,
            headers=headers,
            **kwargs,
        )
        data = response.json()

        if not data.get("ok"):
            error = data.get("error", "unknown_error")
            logger.error(
                "slack_api_error",
                endpoint=endpoint,
                error=error,
            )
            # Map auth-related errors to IntegrationAuthError
            if error in SLACK_AUTH_ERRORS:
                raise IntegrationAuthError(
                    f"Slack auth failed: {error}",
                    provider="slack",
                    details={"error_code": error, "response": data},
                )
            raise SlackAPIError(error, data)

        return data

    async def get_message(
        self,
        channel: str,
        ts: str,
    ) -> dict[str, Any] | None:
        """
        Get a specific message by timestamp.

        Args:
            channel: Channel ID
            ts: Message timestamp

        Returns:
            Message object or None if not found
        """
        try:
            data = await self._request(
                "GET",
                "conversations.history",
                params={
                    "channel": channel,
                    "latest": ts,
                    "inclusive": "true",
                    "limit": "1",
                },
            )

            messages = data.get("messages", [])
            return messages[0] if messages else None

        except SlackAPIError as e:
            logger.error(
                "slack_get_message_failed",
                channel=channel,
                ts=ts,
                error=str(e),
            )
            raise

    async def get_channel_history(
        self,
        channel: str,
        limit: int = 100,
        cursor: str | None = None,
        oldest: str | None = None,
        latest: str | None = None,
    ) -> dict[str, Any]:
        """
        Get channel message history.

        Args:
            channel: Channel ID
            limit: Number of messages to return (max 1000)
            cursor: Pagination cursor
            oldest: Start timestamp (exclusive)
            latest: End timestamp (inclusive)

        Returns:
            Dict with 'messages' list and pagination info
        """
        params: dict[str, Any] = {
            "channel": channel,
            "limit": min(limit, 1000),
        }
        if cursor:
            params["cursor"] = cursor
        if oldest:
            params["oldest"] = oldest
        if latest:
            params["latest"] = latest

        data = await self._request("GET", "conversations.history", params=params)

        return {
            "messages": data.get("messages", []),
            "has_more": data.get("has_more", False),
            "response_metadata": data.get("response_metadata", {}),
        }

    async def get_user_info(self, user_id: str) -> dict[str, Any]:
        """
        Get user profile information.

        Args:
            user_id: Slack user ID

        Returns:
            User object
        """
        data = await self._request(
            "GET",
            "users.info",
            params={"user": user_id},
        )
        return data.get("user", {})

    async def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        """
        Look up user by email address.

        Args:
            email: User email address

        Returns:
            User object or None if not found
        """
        try:
            data = await self._request(
                "GET",
                "users.lookupByEmail",
                params={"email": email},
            )
            return data.get("user")
        except SlackAPIError as e:
            if e.error == "users_not_found":
                return None
            raise

    async def list_channels(
        self,
        limit: int = 100,
        cursor: str | None = None,
        types: str = "public_channel,private_channel",
    ) -> dict[str, Any]:
        """
        List channels the bot is a member of.

        Args:
            limit: Number of channels to return (max 1000)
            cursor: Pagination cursor
            types: Channel types (comma-separated)

        Returns:
            Dict with 'channels' list and pagination info
        """
        params: dict[str, Any] = {
            "limit": min(limit, 1000),
            "types": types,
        }
        if cursor:
            params["cursor"] = cursor

        data = await self._request("GET", "conversations.list", params=params)

        return {
            "channels": data.get("channels", []),
            "response_metadata": data.get("response_metadata", {}),
        }

    async def post_message(
        self,
        channel: str,
        text: str,
        thread_ts: str | None = None,
        blocks: list[dict[str, Any]] | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Post a message to a channel.

        Args:
            channel: Channel ID or name
            text: Message text (required for fallback)
            thread_ts: Thread timestamp to reply to
            blocks: Block Kit blocks (optional)
            attachments: Message attachments (optional)

        Returns:
            Posted message object
        """
        body: dict[str, Any] = {
            "channel": channel,
            "text": text,
        }
        if thread_ts:
            body["thread_ts"] = thread_ts
        if blocks:
            body["blocks"] = blocks
        if attachments:
            body["attachments"] = attachments

        data = await self._request("POST", "chat.postMessage", json=body)

        logger.info(
            "slack_message_posted",
            channel=channel,
            ts=data.get("ts"),
        )

        return {
            "ts": data.get("ts"),
            "channel": data.get("channel"),
            "message": data.get("message"),
        }

    async def add_reaction(
        self,
        channel: str,
        timestamp: str,
        name: str,
    ) -> None:
        """
        Add a reaction to a message.

        Args:
            channel: Channel ID
            timestamp: Message timestamp
            name: Emoji name (without colons)
        """
        await self._request(
            "POST",
            "reactions.add",
            json={
                "channel": channel,
                "timestamp": timestamp,
                "name": name,
            },
        )

    async def get_team_info(self) -> dict[str, Any]:
        """
        Get information about the Slack workspace.

        Returns:
            Team info object
        """
        data = await self._request("GET", "team.info")
        return data.get("team", {})

    async def cleanup(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


class SlackAPIError(Exception):
    """Slack API error."""

    def __init__(self, error: str, response: dict[str, Any] | None = None):
        self.error = error
        self.response = response
        super().__init__(f"Slack API error: {error}")

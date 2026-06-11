"""
Gmail API Client
Uses google-api-python-client for Gmail API access.
"""

import base64
import asyncio
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from core.logging import get_logger
from core.errors import IntegrationAuthError
from services.integration_service import IntegrationService
from core.types import IntegrationType

logger = get_logger("GmailClient")


class GmailClient:
    """
    Gmail API client using google-api-python-client.

    Note: The google-api-python-client is synchronous, so methods use
    run_in_executor to avoid blocking the event loop.

    Docs: https://developers.google.com/gmail/api/guides
    """

    def __init__(self, integration_service: IntegrationService):
        """
        Initialize Gmail client.

        Args:
            integration_service: Service for getting valid tokens
        """
        self.integration_service = integration_service
        self._service = None

    async def _get_service(self):
        """Build Gmail API service with valid credentials."""
        access_token = await self.integration_service.get_valid_token(
            IntegrationType.GMAIL
        )

        # Create credentials object
        credentials = Credentials(token=access_token)

        # Build Gmail API service (runs in executor since it's sync)
        loop = asyncio.get_event_loop()
        service = await loop.run_in_executor(
            None,
            lambda: build("gmail", "v1", credentials=credentials),
        )

        return service

    async def list_messages(
        self,
        user_id: str = "me",
        query: str | None = None,
        max_results: int = 100,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """
        List messages matching query.

        Args:
            user_id: User ID (default 'me' for authenticated user)
            query: Gmail search query (e.g., 'is:unread from:customer@example.com')
            max_results: Maximum messages to return (max 500)
            page_token: Token for pagination

        Returns:
            Dict with 'messages' list and optional 'nextPageToken'
        """
        try:
            service = await self._get_service()

            request_params = {
                "userId": user_id,
                "maxResults": min(max_results, 500),
            }
            if query:
                request_params["q"] = query
            if page_token:
                request_params["pageToken"] = page_token

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: service.users().messages().list(**request_params).execute(),
            )

            messages = result.get("messages", [])
            logger.info("gmail_messages_listed", count=len(messages))

            return {
                "messages": messages,
                "next_page_token": result.get("nextPageToken"),
            }

        except HttpError as e:
            logger.error("gmail_list_messages_failed", error=str(e))
            raise

    async def get_message(
        self,
        message_id: str,
        user_id: str = "me",
        format: str = "full",
    ) -> dict[str, Any]:
        """
        Get a single message.

        Args:
            message_id: Message ID
            user_id: User ID (default 'me')
            format: Message format ('minimal', 'full', 'raw', 'metadata')

        Returns:
            Message object
        """
        try:
            service = await self._get_service()

            loop = asyncio.get_event_loop()
            message = await loop.run_in_executor(
                None,
                lambda: service.users()
                .messages()
                .get(userId=user_id, id=message_id, format=format)
                .execute(),
            )

            return self._parse_message(message)

        except HttpError as e:
            logger.error(
                "gmail_get_message_failed", message_id=message_id, error=str(e)
            )
            raise

    def _parse_message(self, message: dict[str, Any]) -> dict[str, Any]:
        """Parse Gmail message into cleaner format."""
        headers = {}
        if "payload" in message and "headers" in message["payload"]:
            for header in message["payload"]["headers"]:
                headers[header["name"].lower()] = header["value"]

        body = self._extract_body(message.get("payload", {}))

        return {
            "id": message["id"],
            "thread_id": message.get("threadId"),
            "label_ids": message.get("labelIds", []),
            "snippet": message.get("snippet"),
            "from": headers.get("from"),
            "to": headers.get("to"),
            "cc": headers.get("cc"),
            "subject": headers.get("subject"),
            "date": headers.get("date"),
            "body": body,
            "internal_date": message.get("internalDate"),
        }

    def _extract_body(self, payload: dict[str, Any]) -> str:
        """Extract plain text body from message payload."""
        if "body" in payload and payload["body"].get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")

        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain":
                    if part.get("body", {}).get("data"):
                        return base64.urlsafe_b64decode(
                            part["body"]["data"]
                        ).decode("utf-8")
                # Recursively check nested parts
                if "parts" in part:
                    body = self._extract_body(part)
                    if body:
                        return body

        return ""

    async def send_message(
        self,
        to: str,
        subject: str,
        body: str,
        user_id: str = "me",
        thread_id: str | None = None,
        cc: str | None = None,
        bcc: str | None = None,
        html_body: str | None = None,
    ) -> dict[str, Any]:
        """
        Send an email.

        Args:
            to: Recipient email
            subject: Email subject
            body: Email body (plain text)
            user_id: User ID (default 'me')
            thread_id: Thread ID to reply to (optional)
            cc: CC recipients (comma-separated)
            bcc: BCC recipients (comma-separated)
            html_body: HTML version of body (optional)

        Returns:
            Sent message object
        """
        try:
            service = await self._get_service()

            # Create message
            if html_body:
                message = MIMEMultipart("alternative")
                message.attach(MIMEText(body, "plain"))
                message.attach(MIMEText(html_body, "html"))
            else:
                message = MIMEText(body)

            message["to"] = to
            message["subject"] = subject

            if cc:
                message["cc"] = cc
            if bcc:
                message["bcc"] = bcc

            # Encode message
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

            send_body: dict[str, Any] = {"raw": raw}
            if thread_id:
                send_body["threadId"] = thread_id

            loop = asyncio.get_event_loop()
            sent = await loop.run_in_executor(
                None,
                lambda: service.users()
                .messages()
                .send(userId=user_id, body=send_body)
                .execute(),
            )

            logger.info("gmail_message_sent", message_id=sent["id"], to=to)
            return sent

        except HttpError as e:
            logger.error("gmail_send_failed", to=to, error=str(e))
            raise

    async def get_history(
        self,
        start_history_id: str,
        user_id: str = "me",
        history_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Get changes since a history ID (for incremental sync).

        Args:
            start_history_id: Starting history ID (from previous sync or watch)
            user_id: User ID (default 'me')
            history_types: Types to filter ('messageAdded', 'messageDeleted', 'labelAdded', 'labelRemoved')

        Returns:
            Dict with 'history' list and 'historyId'
        """
        try:
            service = await self._get_service()

            request_params = {
                "userId": user_id,
                "startHistoryId": start_history_id,
            }
            if history_types:
                request_params["historyTypes"] = history_types

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: service.users().history().list(**request_params).execute(),
            )

            return {
                "history": result.get("history", []),
                "history_id": result.get("historyId"),
            }

        except HttpError as e:
            logger.error("gmail_get_history_failed", error=str(e))
            raise

    async def setup_watch(
        self,
        topic_name: str,
        user_id: str = "me",
        label_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Setup Gmail push notifications via Pub/Sub.

        Args:
            topic_name: Full Pub/Sub topic name (projects/{project}/topics/{topic})
            user_id: User ID (default 'me')
            label_ids: Label IDs to watch (default ['INBOX'])

        Returns:
            Watch response with 'historyId' and 'expiration'
        """
        try:
            service = await self._get_service()

            request = {
                "labelIds": label_ids or ["INBOX"],
                "topicName": topic_name,
            }

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: service.users()
                .watch(userId=user_id, body=request)
                .execute(),
            )

            logger.info(
                "gmail_watch_enabled",
                history_id=response.get("historyId"),
                expiration=response.get("expiration"),
            )
            return response

        except HttpError as e:
            logger.error("gmail_watch_failed", error=str(e))
            raise

    async def stop_watch(self, user_id: str = "me") -> None:
        """
        Stop Gmail push notifications.

        Args:
            user_id: User ID (default 'me')
        """
        try:
            service = await self._get_service()

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: service.users().stop(userId=user_id).execute(),
            )

            logger.info("gmail_watch_stopped")

        except HttpError as e:
            logger.error("gmail_stop_watch_failed", error=str(e))
            raise

    async def get_thread(
        self,
        thread_id: str,
        user_id: str = "me",
        format: str = "full",
    ) -> dict[str, Any]:
        """
        Get a full thread with all messages.

        Args:
            thread_id: Thread ID
            user_id: User ID (default 'me')
            format: Message format ('minimal', 'full', 'raw', 'metadata')

        Returns:
            Thread object with all messages
        """
        try:
            service = await self._get_service()

            loop = asyncio.get_event_loop()
            thread = await loop.run_in_executor(
                None,
                lambda: service.users()
                .threads()
                .get(userId=user_id, id=thread_id, format=format)
                .execute(),
            )

            # Parse each message in the thread
            messages = [
                self._parse_message(msg)
                for msg in thread.get("messages", [])
            ]

            return {
                "id": thread["id"],
                "snippet": thread.get("snippet"),
                "history_id": thread.get("historyId"),
                "messages": messages,
            }

        except HttpError as e:
            if e.resp.status == 401:
                raise IntegrationAuthError(
                    f"Gmail auth failed: {e}",
                    provider="gmail",
                )
            logger.error(
                "gmail_get_thread_failed", thread_id=thread_id, error=str(e)
            )
            raise

    async def list_messages_since(
        self,
        since: datetime,
        user_id: str = "me",
        label_ids: list[str] | None = None,
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        """
        List messages received after a timestamp.

        Uses Gmail's search query with after: operator for efficient time-windowed queries.

        Args:
            since: Only return messages after this timestamp
            user_id: User ID (default 'me')
            label_ids: Filter by label IDs (default ['INBOX'])
            max_results: Maximum messages to return

        Returns:
            List of parsed message objects
        """
        try:
            # Convert datetime to Unix timestamp for Gmail query
            # Gmail's after: uses epoch seconds
            since_ts = int(since.timestamp())
            query = f"after:{since_ts}"

            # Get message IDs
            result = await self.list_messages(
                user_id=user_id,
                query=query,
                max_results=max_results,
            )

            message_ids = [msg["id"] for msg in result.get("messages", [])]

            # Fetch full messages in parallel
            messages = []
            for msg_id in message_ids:
                try:
                    msg = await self.get_message(msg_id, user_id=user_id)
                    messages.append(msg)
                except HttpError as e:
                    if e.resp.status == 401:
                        raise IntegrationAuthError(
                            f"Gmail auth failed: {e}",
                            provider="gmail",
                        )
                    logger.warning(
                        "gmail_message_fetch_failed",
                        message_id=msg_id,
                        error=str(e),
                    )
                    continue

            logger.info(
                "gmail_messages_fetched_since",
                since=since.isoformat(),
                count=len(messages),
            )

            return messages

        except HttpError as e:
            if e.resp.status == 401:
                raise IntegrationAuthError(
                    f"Gmail auth failed: {e}",
                    provider="gmail",
                )
            logger.error("gmail_list_messages_since_failed", error=str(e))
            raise

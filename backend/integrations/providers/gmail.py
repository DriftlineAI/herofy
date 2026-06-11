"""
Gmail OAuth Provider
Implements OAuth 2.0 for Gmail and Google Calendar API access.
"""

from typing import Any

from integrations.providers.base import BaseOAuthProvider


class GmailOAuthProvider(BaseOAuthProvider):
    """
    Gmail OAuth provider using Google's OAuth 2.0.

    Scopes:
    - gmail.readonly: Read emails
    - gmail.send: Send emails
    - gmail.modify: Manage labels, archive
    - calendar.readonly: Read calendar events
    - calendar.events: Create/edit calendar events

    Docs: https://developers.google.com/identity/protocols/oauth2
    """

    @property
    def provider_name(self) -> str:
        return "gmail"

    @property
    def authorization_endpoint(self) -> str:
        return "https://accounts.google.com/o/oauth2/v2/auth"

    @property
    def token_endpoint(self) -> str:
        return "https://oauth2.googleapis.com/token"

    @property
    def revocation_endpoint(self) -> str:
        return "https://oauth2.googleapis.com/revoke"

    def get_client_credentials(self) -> tuple[str, str]:
        """Get Google OAuth credentials from config."""
        client_id = self.config.google_client_id
        client_secret = self.config.google_client_secret

        if not client_id or not client_secret:
            raise ValueError(
                "Gmail OAuth credentials not configured "
                "(google_client_id/google_client_secret)"
            )

        return client_id, client_secret

    def get_default_scopes(self) -> list[str]:
        """Default Gmail and Calendar API scopes."""
        return [
            # Gmail scopes
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.modify",
            # Calendar scopes
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/calendar.events",
        ]

    def _customize_auth_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Add Google-specific parameters."""
        # Request offline access for refresh token
        params["access_type"] = "offline"
        # Force consent screen to get refresh token every time
        params["prompt"] = "consent"
        return params

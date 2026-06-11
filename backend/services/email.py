"""
Email service using Resend.

Simple text-based emails for transactional notifications.
"""

import resend
from typing import Optional

from config import settings
from core.logging import get_logger

logger = get_logger("email")


def init_resend():
    """Initialize Resend with API key."""
    if settings.resend_api_key:
        resend.api_key = settings.resend_api_key


async def send_email(
    to: str,
    subject: str,
    text: str,
    html: Optional[str] = None,
    from_email: Optional[str] = None,
) -> dict:
    """
    Send an email via Resend.

    Args:
        to: Recipient email address
        subject: Email subject
        text: Plain text email body
        html: Optional HTML email body
        from_email: Optional from address (defaults to settings.resend_from_email)

    Returns:
        Response dict from Resend API

    Raises:
        Exception if Resend API key is not configured
    """
    if not settings.resend_api_key:
        logger.warning("email_skipped", reason="no_api_key", to=to, subject=subject)
        return {"status": "skipped", "reason": "no_api_key"}

    from_addr = from_email or settings.resend_from_email

    try:
        params = {
            "from": from_addr,
            "to": [to],
            "subject": subject,
            "text": text,
        }

        if html:
            params["html"] = html

        response = resend.Emails.send(params)

        logger.info(
            "email_sent",
            to=to,
            subject=subject,
            email_id=response.get("id"),
        )

        return response

    except Exception as e:
        logger.error("email_failed", to=to, subject=subject, error=str(e))
        raise


# ==============================================================================
# Template Emails
# ==============================================================================


async def send_waitlist_confirmation(email: str) -> dict:
    """Send confirmation email to waitlist signup."""
    subject = "You're on the Herofy waitlist!"
    text = f"""Thanks for joining the Herofy waitlist!

We're building an AI-powered workspace for small B2B SaaS customer success teams.

We'll keep you updated on our progress and let you know when Herofy is ready for you.

— The Herofy Team
https://herofy.ai
"""

    return await send_email(to=email, subject=subject, text=text)


async def send_waitlist_notification(email: str) -> dict:
    """Send notification to team about new waitlist signup."""
    subject = f"New waitlist signup: {email}"
    text = f"""New waitlist signup:

Email: {email}
Timestamp: Just now

View all signups in the backend data folder or database.
"""

    return await send_email(
        to=settings.resend_notify_email,
        subject=subject,
        text=text,
    )


async def send_join_request_notification(
    workspace_name: str,
    workspace_id: str,
    requester_email: str,
    requester_name: Optional[str],
    owner_email: str,
) -> dict:
    """Send notification to workspace owner about join request."""
    requester_display = requester_name or requester_email
    app_url = settings.get_app_base_url_with_fallback()

    subject = f"{requester_display} wants to join {workspace_name}"
    text = f"""New workspace join request:

Workspace: {workspace_name}
Requester: {requester_display} ({requester_email})

To approve or reject this request, log in to Herofy:
{app_url}/settings/team

— Herofy
"""

    return await send_email(
        to=owner_email,
        subject=subject,
        text=text,
    )


# Initialize Resend on module import
init_resend()


async def send_invitation_email(
    to_email: str,
    workspace_name: str,
    inviter_name: str,
    invite_link: str,
    role: str,
) -> dict:
    """Send invitation email to join workspace."""
    subject = f"{inviter_name} invited you to join {workspace_name} on Herofy"
    text = f"""Hi there,

{inviter_name} has invited you to join the {workspace_name} workspace on Herofy as a {role}.

Click the link below to accept the invitation:
{invite_link}

This invitation will expire in 7 days.

If you don't have a Herofy account yet, you'll be able to create one when you accept the invitation.

— Herofy
"""

    return await send_email(
        to=to_email,
        subject=subject,
        text=text,
    )

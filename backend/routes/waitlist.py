"""Waitlist route - collect email signups."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from core.logging import get_logger
from db.dataconnect_client import get_dataconnect_client
from services.email import send_waitlist_confirmation, send_waitlist_notification

router = APIRouter(tags=["waitlist"])
logger = get_logger("waitlist")


class WaitlistSignup(BaseModel):
    email: EmailStr


class WaitlistResponse(BaseModel):
    success: bool
    message: str


@router.post("/api/waitlist", response_model=WaitlistResponse)
async def join_waitlist(signup: WaitlistSignup):
    """
    Add an email to the waitlist.

    Stores to database and sends:
    - Confirmation email to the user
    - Notification email to info@herofy.ai
    """
    email = signup.email.lower().strip()

    try:
        dc = get_dataconnect_client()

        # Check if already signed up
        existing = await dc.execute_query(
            "CheckWaitlistEmail",
            {"email": email},
        )

        if existing.get("waitlistSignups"):
            logger.info("waitlist_duplicate", email=email)
            return WaitlistResponse(
                success=True,
                message="You're already on the list!"
            )

        # Add to database
        await dc.execute_mutation(
            "CreateWaitlistSignup",
            {"email": email},
        )

        logger.info("waitlist_signup", email=email)

        # Send emails (best effort - don't fail if emails fail)
        try:
            await send_waitlist_confirmation(email)
        except Exception as e:
            logger.warning("waitlist_confirmation_failed", email=email, error=str(e))

        try:
            await send_waitlist_notification(email)
        except Exception as e:
            logger.warning("waitlist_notification_failed", email=email, error=str(e))

        return WaitlistResponse(
            success=True,
            message="You're on the list!"
        )

    except Exception as e:
        logger.error("waitlist_error", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to join waitlist")

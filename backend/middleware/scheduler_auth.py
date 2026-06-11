"""
Cloud Scheduler OIDC Authentication Middleware
Verifies JWT tokens from Google Cloud Scheduler.
"""

from typing import Optional

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import settings
from core.logging import get_logger

logger = get_logger("scheduler_auth")

# HTTP Bearer token extractor (optional - scheduler may not send token in dev)
security = HTTPBearer(auto_error=False)


async def verify_scheduler_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> bool:
    """
    Verify OIDC token from Cloud Scheduler.

    In development mode, bypasses authentication.
    In production, verifies:
    - JWT signature using Google's public keys
    - Audience matches our service URL
    - Issuer is accounts.google.com

    Args:
        request: FastAPI request
        credentials: Optional Bearer token

    Returns:
        True if verified

    Raises:
        HTTPException: If verification fails in production
    """
    # Development bypass
    if settings.is_development:
        logger.debug("scheduler_auth_bypassed", reason="development_mode")
        return True

    # Production requires token
    if credentials is None:
        logger.warning(
            "scheduler_auth_failed",
            reason="missing_token",
            path=request.url.path,
        )
        raise HTTPException(
            status_code=403,
            detail="Authorization token required for scheduler endpoint",
        )

    token = credentials.credentials

    try:
        # Import google-auth for OIDC verification
        from google.oauth2 import id_token
        from google.auth.transport import requests

        # Get expected audience from settings
        expected_audience = settings.poll_service_url
        if not expected_audience:
            logger.error("scheduler_auth_failed", reason="poll_service_url_not_configured")
            raise HTTPException(
                status_code=500,
                detail="Server misconfiguration: poll_service_url not set",
            )

        # Verify the token
        # This checks:
        # - Token signature (using Google's public keys)
        # - Token expiration
        # - Audience claim matches our service
        # - Issuer is accounts.google.com
        id_info = id_token.verify_oauth2_token(
            token,
            requests.Request(),
            audience=expected_audience,
        )

        # Optionally verify service account email
        email = id_info.get("email", "")
        expected_sa = settings.cloud_scheduler_service_account
        if expected_sa and email != expected_sa:
            logger.warning(
                "scheduler_auth_failed",
                reason="service_account_mismatch",
                expected=expected_sa,
                actual=email,
            )
            raise HTTPException(
                status_code=403,
                detail="Invalid service account",
            )

        logger.debug(
            "scheduler_auth_success",
            service_account=email,
        )
        return True

    except ValueError as e:
        # Token verification failed
        logger.warning(
            "scheduler_auth_failed",
            reason="invalid_token",
            error=str(e),
        )
        raise HTTPException(
            status_code=403,
            detail=f"Invalid OIDC token: {e}",
        )
    except ImportError:
        # google-auth not installed - fail gracefully in dev
        if settings.is_development:
            logger.warning("scheduler_auth_bypassed", reason="google_auth_not_installed")
            return True
        raise HTTPException(
            status_code=500,
            detail="Server misconfiguration: google-auth not installed",
        )

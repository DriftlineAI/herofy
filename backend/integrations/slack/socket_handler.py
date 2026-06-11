"""
Slack Socket Mode Handler
WebSocket-based event listener for development
"""

from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from core.logging import get_logger

logger = get_logger("SlackSocketMode")


async def start_socket_mode():
    """
    Start Socket Mode listener (development only).

    Blocks until connection closes. Should be run as background task
    in FastAPI lifespan context.

    Raises:
        ValueError: If SLACK_APP_TOKEN not configured
    """
    from config import settings
    from .bolt_app import get_bolt_app

    if settings.slack_mode != "socket":
        logger.info("Socket Mode not enabled (SLACK_MODE != 'socket')")
        return

    if not settings.slack_app_token:
        logger.error("SLACK_APP_TOKEN required for Socket Mode")
        raise ValueError("SLACK_APP_TOKEN not configured")

    if not settings.slack_bot_token:
        logger.error("SLACK_BOT_TOKEN required for Socket Mode")
        raise ValueError("SLACK_BOT_TOKEN not configured")

    logger.info(
        "socket_mode_starting",
        mode=settings.slack_mode,
        has_app_token=bool(settings.slack_app_token),
        has_bot_token=bool(settings.slack_bot_token),
    )

    app = get_bolt_app()
    handler = AsyncSocketModeHandler(app, settings.slack_app_token)

    # Start handler (blocks until connection closes)
    # Bolt SDK handles auto-reconnect with exponential backoff
    await handler.start_async()

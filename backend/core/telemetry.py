"""
Langfuse v4 telemetry via OpenTelemetry.

Langfuse v4 registers itself as the global OTel TracerProvider on init.
openinference-instrumentation-google-adk then auto-instruments every ADK
agent call, tool call, and model completion as OTel spans exported to Langfuse.

Setup (called once at server startup after load_dotenv()):
    setup_langfuse()

Per-task enrichment (in consumer):
    async with task_trace(name, input, session_id, user_id):
        # run worker — ADK spans auto-nest inside this span

No-ops gracefully when LANGFUSE_SECRET_KEY is unset or packages are missing.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from core.logging import get_logger

logger = get_logger("Telemetry")

_setup_done = False


def setup_langfuse() -> bool:
    """
    One-time startup: create Langfuse client (registers global OTel provider)
    and instrument Google ADK. Returns True if telemetry is active.

    Must be called AFTER load_dotenv() so credentials are in the environment.
    """
    global _setup_done
    if _setup_done:
        return True

    from config import get_settings
    s = get_settings()
    if not s.langfuse_secret_key:
        logger.info("langfuse_disabled", reason="LANGFUSE_SECRET_KEY not set")
        return False

    try:
        from langfuse import Langfuse

        # Creating Langfuse registers itself as the global OTel TracerProvider.
        Langfuse(
            public_key=s.langfuse_public_key,
            secret_key=s.langfuse_secret_key,
            host=s.langfuse_host or "https://cloud.langfuse.com",
        )

        # Auto-instrument Google ADK — captures all LlmAgent calls, tool calls,
        # and model completions (including token counts) as nested OTel spans.
        from openinference.instrumentation.google_adk import GoogleADKInstrumentor
        GoogleADKInstrumentor().instrument()

        _setup_done = True
        logger.info("langfuse_enabled", host=s.langfuse_host or "https://cloud.langfuse.com")
        return True

    except ImportError as e:
        logger.warning("langfuse_setup_skipped", reason=f"missing package: {e}")
        return False
    except Exception as e:
        logger.warning("langfuse_setup_failed", error=str(e))
        return False


@asynccontextmanager
async def task_trace(
    name: str,
    *,
    input: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
):
    """
    Async context manager that wraps one AgentTask run in a Langfuse root span.

    ADK spans created inside are automatically nested under it via OTel context
    propagation. session_id groups all workspace activity in Langfuse Sessions;
    user_id attributes cost/quality per customer.
    """
    if not _setup_done:
        yield None
        return

    try:
        from langfuse import get_client, propagate_attributes

        langfuse = get_client()
        with langfuse.start_as_current_observation(
            name=name,
            as_type="span",
            input=input or {},
        ) as span:
            tags = []
            if session_id:
                tags.append(f"workspace:{session_id}")
            if user_id:
                tags.append(f"customer:{user_id}")

            with propagate_attributes(
                session_id=session_id,
                user_id=user_id,
                metadata={k: str(v) for k, v in (metadata or {}).items()},
                trace_name=name,
                tags=tags or None,
            ):
                try:
                    yield span
                except Exception as e:
                    try:
                        span.update(level="ERROR", status_message=str(e)[:500])
                    except Exception:
                        pass
                    raise
    except ImportError:
        yield None
    except Exception as e:
        logger.warning("task_trace_failed", error=str(e))
        yield None


def get_langfuse():
    """Return the Langfuse client if configured, else None."""
    if not _setup_done:
        return None
    try:
        from langfuse import get_client
        return get_client()
    except Exception:
        return None

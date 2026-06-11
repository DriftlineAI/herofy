"""
Cross-cutting callbacks for the orchestrator (ADK-native, not bespoke loops).

Phase 0 ships the progress-streaming hooks: a single `before/after_agent_callback`
pair that streams stage handoffs to Firestore (`agent_status/{run_id}`), so the UI
lights up as the worker reasons and each play stage runs. The same `stream_status`
helper is called directly by the queue consumer for claim/complete transitions.

Guardrail / memory-load callbacks attach here too (memory-load lives in the
memory/ module and is composed in Phase 0; model guardrails in Phase 1+).
"""

import json
from typing import Any

from google.adk.agents.callback_context import CallbackContext

from core.logging import get_logger
from services.firestore_service import get_firestore_service

from .state import (
    KEY_RUN_ID,
    KEY_CUSTOMER_ID,
    KEY_CUSTOMER_NAME,
    temp_key,
)

logger = get_logger("OrchestratorCallbacks")

_PROGRESS_KEY = temp_key("progress_pct")


async def stream_status(
    run_id: str,
    status: str,
    step: str,
    message: str,
    progress_pct: int = 50,
    customer_id: str | None = None,
    customer_name: str | None = None,
) -> None:
    """Best-effort live status write. Never raises into agent/consumer flow.

    Writes both the live single-doc status (for progress/terminal display) and an append-only
    entry to the steps subcollection (so the Lab can reconstruct the true path without losing
    rapidly-overwritten steps)."""
    try:
        svc = get_firestore_service()
        await svc.update_agent_status(
            run_id=run_id,
            status=status,
            step=step,
            progress_pct=progress_pct,
            message=message,
            customer_id=customer_id,
            customer_name=customer_name,
        )
        await svc.append_step(run_id=run_id, step=step, status=status, progress_pct=progress_pct)
    except Exception as e:  # streaming is non-fatal
        logger.warning("orchestrator_stream_status_failed", error=str(e), step=step)


def _ctx_get(callback_context: CallbackContext, key: str) -> Any:
    try:
        return callback_context.state.get(key)
    except Exception:
        return None


async def before_agent_callback(callback_context: CallbackContext):
    """Stream a 'stage starting' status keyed on the agent name. Returns None to
    let the agent run normally."""
    run_id = _ctx_get(callback_context, KEY_RUN_ID)
    if not run_id:
        return None

    pct = _ctx_get(callback_context, _PROGRESS_KEY) or 10
    step = callback_context.agent_name or "thinking"
    await stream_status(
        run_id=run_id,
        status="running",
        step=step,
        message=f"{step}…",
        progress_pct=int(pct),
        customer_id=_ctx_get(callback_context, KEY_CUSTOMER_ID),
        customer_name=_ctx_get(callback_context, KEY_CUSTOMER_NAME),
    )
    return None


async def after_agent_callback(callback_context: CallbackContext):
    """Advance the progress counter as each stage finishes. Returns None."""
    run_id = _ctx_get(callback_context, KEY_RUN_ID)
    if not run_id:
        return None

    pct = (_ctx_get(callback_context, _PROGRESS_KEY) or 10) + 15
    pct = min(int(pct), 90)
    try:
        callback_context.state[_PROGRESS_KEY] = pct
    except Exception:
        pass

    step = callback_context.agent_name or "step"
    await stream_status(
        run_id=run_id,
        status="running",
        step=step,
        message=f"{step} done",
        progress_pct=pct,
        customer_id=_ctx_get(callback_context, KEY_CUSTOMER_ID),
        customer_name=_ctx_get(callback_context, KEY_CUSTOMER_NAME),
    )
    return None


def _llm_text(llm_response) -> str:
    """Concatenate text parts of a model response, guarding `parts is None`."""
    try:
        content = getattr(llm_response, "content", None)
        parts = getattr(content, "parts", None) or []
        return "\n".join(p.text for p in parts if getattr(p, "text", None)).strip()
    except Exception:
        return ""


def _llm_function_calls(llm_response) -> list[str]:
    """Names of any function calls the model emitted (so the Lab can show 'decided to call X')."""
    names: list[str] = []
    try:
        content = getattr(llm_response, "content", None)
        for p in (getattr(content, "parts", None) or []):
            fc = getattr(p, "function_call", None)
            if fc and getattr(fc, "name", None):
                names.append(fc.name)
    except Exception:
        pass
    return names


async def stream_model_output(callback_context, llm_response) -> None:
    """Capture one LLM agent's model output to agent_status/{runId}/outputs for the Lab trace
    view. Wired centrally via every agent's after_model_callback. Best-effort; never raises."""
    run_id = _ctx_get(callback_context, KEY_RUN_ID)
    if not run_id or llm_response is None:
        return
    text = _llm_text(llm_response)
    fcs = _llm_function_calls(llm_response)
    if not text and not fcs:
        return
    try:
        await get_firestore_service().append_agent_output(
            run_id=run_id,
            agent_name=getattr(callback_context, "agent_name", None) or "agent",
            text=text,
            function_calls=fcs,
        )
    except Exception as e:  # streaming is non-fatal
        logger.warning("stream_model_output_failed", error=str(e))


async def stream_tool_output(tool, args, tool_context, tool_response):
    """Capture a tool's RESULT to agent_status/{runId}/outputs for the Lab trace view, so the
    panel shows what get_customer_info / recall / google_search / a play actually returned (not
    just that the model called it). Wired as after_tool_callback. Returns None to keep the
    original response; best-effort and never raises."""
    try:
        run_id = tool_context.state.get(KEY_RUN_ID)
    except Exception:
        run_id = None
    if not run_id:
        return None
    if isinstance(tool_response, str):
        text = tool_response
    else:
        try:
            text = json.dumps(tool_response, default=str)
        except Exception:
            text = str(tool_response)
    if not text:
        return None
    try:
        await get_firestore_service().append_agent_output(
            run_id=run_id,
            agent_name=getattr(tool, "name", None) or "tool",
            text=text,
            kind="tool",
        )
    except Exception as e:  # streaming is non-fatal
        logger.warning("stream_tool_output_failed", error=str(e))
    return None


from .langfuse_callbacks import after_model_callback_langfuse as langfuse_model_cb  # noqa: E402  re-export

"""
Support play — deterministic SequentialAgent (Research → Triage → Draft → Surface).

A support-rep lens (not a CSM): understand the reported issue, draft an on-voice reply,
surface it for review. Bounded to triage + draft + route — NOT ticket resolution.
LLM stages produce content; the deterministic stage persists a real DraftResponse +
surfaces a Need so it renders on the thread and need screens. Dispatched by the worker
for technical / urgent_support tasks.
"""

import json
from typing import AsyncGenerator

from google.adk.agents import BaseAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.genai import types

from core.logging import get_logger

from .. import artifacts
from ..runtime.callbacks import before_agent_callback
from ..runtime.state import KEY_WORKSPACE_ID, KEY_CUSTOMER_ID, KEY_CUSTOMER_NAME, KEY_RUN_ID, KEY_PAYLOAD
from ..specialists import build_researcher, build_technical_triage, build_support_responder
from ..specialists.support import TRIAGE_KEY, SUPPORT_RESPONSE_KEY

logger = get_logger("SupportPlay")

STATE_DRAFT_ID = "support_draft_id"
STATE_SUPPORT_NEED_ID = "support_need_id"


def _parse(state, key) -> dict | None:
    v = state.get(key)
    if isinstance(v, str):
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return None
    if isinstance(v, dict):
        return v
    if hasattr(v, "model_dump"):
        return v.model_dump()
    return None


def _event(author: str, text: str) -> Event:
    return Event(author=author, content=types.Content(role="model", parts=[types.Part(text=text)]))


class PersistSupportReply(BaseAgent):
    """Surface a support Need + write the drafted reply (DraftResponse) linked to it.
    If triage flagged engineering, drop an internal observation to alert the team."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        triage = _parse(state, TRIAGE_KEY) or {}
        reply = _parse(state, SUPPORT_RESPONSE_KEY)
        workspace_id = state.get(KEY_WORKSPACE_ID)
        customer_id = state.get(KEY_CUSTOMER_ID)
        customer_name = state.get(KEY_CUSTOMER_NAME) or "the customer"
        payload = state.get(KEY_PAYLOAD) or {}
        run_id = state.get(KEY_RUN_ID)
        if not reply or not workspace_id or not customer_id:
            yield _event(self.name, "No support reply to persist; skipping.")
            return

        severity = triage.get("severity", "medium")
        needs_eng = bool(triage.get("needs_engineering"))
        # High-severity / eng issues read as urgent_support; otherwise a ready draft to review.
        need_type = "urgent_support" if (severity == "high" or needs_eng) else "draft_response_ready"
        summary = triage.get("summary") or "Support reply drafted."

        need_id = await artifacts.surface_need(
            workspace_id, customer_id,
            need_type=need_type,
            headline=f"{customer_name}: {summary}",
            lede=triage.get("impact") or "A drafted reply is ready for your review.",
            reasoning=f"{triage.get('impact','')} (severity: {severity}"
                      + (", engineering likely" if needs_eng else "") + ")",
            source_event_id=payload.get("source_event_id"),
            agent_run_id=run_id,
            priority_rank=3 if need_type == "urgent_support" else 8,
            thread_id=payload.get("thread_id"),
        )
        state[STATE_SUPPORT_NEED_ID] = need_id

        draft_id = await artifacts.create_draft_response(
            workspace_id, customer_id,
            body=reply.get("body", ""),
            subject=reply.get("subject"),
            thread_id=payload.get("thread_id"),
            surfaced_in_need_id=need_id,
        )
        state[STATE_DRAFT_ID] = draft_id

        if needs_eng:
            await artifacts.record_observation(
                workspace_id, customer_id,
                text=f"Likely an engineering issue ({severity}) — flag to eng: {triage.get('impact','')}",
                agent_run_id=run_id, kind="observed",
            )
        logger.info("support_reply_persisted", need_id=need_id, draft_id=draft_id,
                    need_type=need_type, needs_engineering=needs_eng)
        yield _event(self.name, f"Drafted a reply for {customer_name} and surfaced it ({need_type}).")


def build_support_play(workspace_id: str, customer_id: str, notion_token: str | None = None, after_agent_callback=None) -> SequentialAgent:
    """Compose the Support play for one account."""
    return SequentialAgent(
        name="support_play",
        before_agent_callback=before_agent_callback,  # stream the play root at start (reveals the Lab subtree immediately)
        description=(
            "Run for technical issues, support questions, bugs, or customer complaints. "
            "Triages the problem, drafts a reply email addressing the issue, and surfaces "
            "an urgent_support Need in the CSM's queue for review before sending."
        ),
        sub_agents=[
            build_researcher(workspace_id, customer_id, notion_token=notion_token, after_agent_callback=after_agent_callback),
            build_technical_triage(after_agent_callback=after_agent_callback),
            build_support_responder(after_agent_callback=after_agent_callback),
            PersistSupportReply(name="persist_support_reply", after_agent_callback=after_agent_callback),
        ],
    )

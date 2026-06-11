"""
Meeting-brief play — deterministic SequentialAgent (Research → Writer → Persist → Surface).

Reuses the existing (now-fixed, idempotent) `create_meeting_brief` tool to persist, and
surfaces a `meeting_prep_ready` Need. Same shape as the risk/save play: LLM stages produce
content, deterministic stages persist it. Dispatched by the worker for meeting-prep tasks.
"""

import json
from typing import AsyncGenerator

from google.adk.agents import BaseAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.genai import types

from core.logging import get_logger

# Reused tool callable from the working agent (sanctioned: reuse services, not the agent).
from agents.handoff_auto.tools.artifacts import create_meeting_brief as _create_meeting_brief

from .. import artifacts
from ..runtime.callbacks import before_agent_callback
from ..runtime.state import KEY_WORKSPACE_ID, KEY_CUSTOMER_ID, KEY_CUSTOMER_NAME, KEY_RUN_ID, KEY_PAYLOAD
from ..specialists import build_researcher, build_meeting_writer
from ..specialists.meeting_writer import MEETING_BRIEF_KEY

logger = get_logger("MeetingBriefPlay")

STATE_MEETING_BRIEF_ID = "meeting_brief_id"
STATE_MEETING_NEED_ID = "meeting_need_id"
MEETING_NEED_TYPE = "meeting_prep_ready"


def _brief(state) -> dict | None:
    v = state.get(MEETING_BRIEF_KEY)
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


class PersistMeetingBrief(BaseAgent):
    """Write the MeetingBrief via the reused (idempotent) create_meeting_brief tool."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        mb = _brief(state)
        workspace_id = state.get(KEY_WORKSPACE_ID)
        customer_name = state.get(KEY_CUSTOMER_NAME) or "the customer"
        payload = state.get(KEY_PAYLOAD) or {}
        meeting_id = payload.get("meeting_id")
        if not mb or not workspace_id or not meeting_id:
            yield _event(self.name, "No meeting brief / meeting id to persist; skipping.")
            return

        followup_email = mb.get("followup_email")
        result = await _create_meeting_brief(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            customer_name=customer_name,
            progress_narrative=mb.get("progress_narrative", ""),
            talking_points_json=json.dumps(mb.get("talking_points") or []),
            progress_facts_json=json.dumps(mb.get("progress_facts") or []),
            friction=mb.get("friction") or None,
            value_delivered=mb.get("value_delivered") or None,
            risk_to_renewal=mb.get("risk_to_renewal") or None,
            expansion_signals=mb.get("expansion_signals") or None,
            followup_email_json=json.dumps(followup_email) if followup_email else None,
        )
        brief_id = result.get("brief_id") if isinstance(result, dict) else None
        if not brief_id:
            logger.error("meeting_brief_persist_failed", meeting_id=meeting_id, result=str(result)[:200])
            yield _event(self.name, f"Could not persist meeting brief: {result.get('error') if isinstance(result, dict) else result}")
            return
        state[STATE_MEETING_BRIEF_ID] = brief_id
        logger.info("meeting_brief_persisted", brief_id=brief_id, meeting_id=meeting_id)
        yield _event(self.name, f"Wrote meeting brief ({result.get('status')}) for {customer_name}.")


class SurfaceMeetingNeed(BaseAgent):
    """Surface a meeting_prep_ready Need in the Today queue."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        mb = _brief(state)
        workspace_id = state.get(KEY_WORKSPACE_ID)
        customer_id = state.get(KEY_CUSTOMER_ID)
        customer_name = state.get(KEY_CUSTOMER_NAME) or "the customer"
        payload = state.get(KEY_PAYLOAD) or {}
        if not mb or not workspace_id or not customer_id:
            yield _event(self.name, "No meeting brief to surface; skipping.")
            return

        source_event_id = payload.get("source_event_id")
        # (Dedupe is now per (event + need_type), centralized in artifacts.surface_need.)
        meeting_title = payload.get("meeting_title") or "upcoming meeting"
        tps = mb.get("talking_points") or []
        need_id = await artifacts.surface_need(
            workspace_id, customer_id,
            need_type=MEETING_NEED_TYPE,
            headline=f"{customer_name}: prep for {meeting_title}",
            lede=(tps[0] if tps else "Meeting brief ready — review before the call."),
            reasoning=(mb.get("progress_narrative", "") or "")[:300],
            source_event_id=source_event_id,
            agent_run_id=state.get(KEY_RUN_ID),
            priority_rank=8,
            thread_id=payload.get("thread_id"),
        )
        state[STATE_MEETING_NEED_ID] = need_id
        logger.info("meeting_need_surfaced", need_id=need_id, meeting_id=payload.get("meeting_id"))
        yield _event(self.name, "Surfaced a meeting-prep Need in the Today queue.")


def build_meeting_brief_play(workspace_id: str, customer_id: str, notion_token: str | None = None, after_agent_callback=None) -> SequentialAgent:
    """Compose the meeting-brief play for one account."""
    return SequentialAgent(
        name="meeting_brief_play",
        before_agent_callback=before_agent_callback,  # stream the play root at start (reveals the Lab subtree immediately)
        description=(
            "Run when there is an upcoming customer meeting. Prepares a meeting brief with "
            "talking points, progress summary, risk-to-renewal assessment, and customer context. "
            "Surfaces a meeting_prep_ready Need so the CSM has everything ready before the call."
        ),
        sub_agents=[
            build_researcher(workspace_id, customer_id, notion_token=notion_token, after_agent_callback=after_agent_callback),
            build_meeting_writer(after_agent_callback=after_agent_callback),
            PersistMeetingBrief(name="persist_meeting_brief", after_agent_callback=after_agent_callback),
            SurfaceMeetingNeed(name="surface_meeting_need", after_agent_callback=after_agent_callback),
        ],
    )

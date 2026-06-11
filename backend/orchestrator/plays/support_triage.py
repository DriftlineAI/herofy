"""
Inbound support triage — the LIGHT lane (Lane 1).

The high-volume path for ordinary inbound: classify → assess risk → draft → surface.
No PlanReActPlanner, no autonomous tool loop, no researcher LLM call — two LLM calls
(classify + draft) wrapped around a DETERMINISTIC risk analyst and a deterministic
persist stage. This is the ~$0.005 path that most support traffic should take.

The risk_analyst is the seam that keeps cost AND quality in line: it reads the
customer's existing risk posture (active signals, open risk needs, lifecycle, renewal
proximity) and combines it with THIS message's sentiment. A simple question from a
healthy account → a plain drafted reply. The same simple question from an at-risk
account, or any angry message → the package escalates: the draft still goes out, but
we also surface an escalation Need and hand off a risk_save_play to the worker (Lane 2).

LLM stages produce content; deterministic stages decide and persist. Same architecture
principle as risk_save_play — autonomy only where there's a real decision (there's none
here), determinism at the execution layer.
"""

import json
from typing import AsyncGenerator

from google.adk.agents import BaseAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

from core.logging import get_logger
from db.dataconnect_client import get_dataconnect_client

from .. import artifacts
from ..runtime.state import (
    KEY_WORKSPACE_ID, KEY_CUSTOMER_ID, KEY_CUSTOMER_NAME, KEY_RUN_ID, KEY_PAYLOAD,
)
from ..specialists import build_inbound_classifier
from ..specialists.support import INBOUND_CLASS_KEY
from ..specialists.schemas import SupportResponseOutput

logger = get_logger("SupportTriagePlay")

RISK_POSTURE_KEY = "risk_posture"
ACCOUNT_CONTEXT_KEY = "account_context"
INBOUND_RESPONSE_KEY = "inbound_response"

STATE_DRAFT_ID = "inbound_draft_id"
STATE_NEED_ID = "inbound_need_id"
STATE_ESCALATED = "inbound_escalated"


class _SkipHandoff(Exception):
    """Internal sentinel — an active task already exists, so skip the Lane-2 enqueue."""


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


# ---------------------------------------------------------------------------
# Deterministic risk analyst — no LLM. Reads existing posture + new sentiment.
# ---------------------------------------------------------------------------

# Sentiment from THIS message → contribution to the risk score.
_SENTIMENT_SCORE = {"angry": 3, "frustrated": 2, "negative": 1, "neutral": 0, "positive": 0}


async def assess_inbound_risk(workspace_id: str, customer_id: str, new_sentiment: str) -> dict:
    """Deterministic risk posture — combine the account's STANDING risk (active signals,
    open risk needs, lifecycle, renewal proximity) with THIS message's sentiment. No LLM.

    NOTE: this is called from the PERSIST stage, not as its own sub-agent. An LlmAgent's
    output_key lands as a lagged state_delta the Runner applies AFTER the next sub-agent
    starts — so a sub-agent immediately after the classifier reads stale state. The persist
    stage runs late enough that the classifier's delta is reliably applied."""
    score = 0
    factors: list[str] = []
    customer: dict = {}
    signals: list = []
    open_needs: list = []

    try:
        dc = get_dataconnect_client()
        res = await dc.execute_query(
            "GetCustomerRiskContext",
            {"workspaceId": workspace_id, "customerId": customer_id},
        )
        customer = res.get("customer") or {}
        signals = customer.get("signals_on_customer") or []
        open_needs = res.get("needs") or []
    except Exception as e:
        logger.warning("risk_context_load_failed", customer_id=customer_id, error=str(e))

    if any(s.get("state") == "risk" for s in signals):
        score += 3
        factors.append("active risk-state signal on the account")
    elif any(s.get("state") == "warn" for s in signals):
        score += 1
        factors.append("active warn-state signal on the account")

    if open_needs:
        score += 3
        factors.append(f"open risk need(s): {', '.join(n.get('type','') for n in open_needs)}")

    lifecycle = customer.get("lifecycle")
    if lifecycle in ("at_risk", "churned"):
        score += 3
        factors.append(f"lifecycle is {lifecycle}")

    days_to_renewal = customer.get("daysToRenewal")
    if isinstance(days_to_renewal, int) and 0 <= days_to_renewal <= 60:
        score += 1
        factors.append(f"renewal in {days_to_renewal} days")

    sentiment_score = _SENTIMENT_SCORE.get(new_sentiment, 0)
    if sentiment_score:
        score += sentiment_score
        factors.append(f"this message reads as {new_sentiment}")

    level = "high" if score >= 3 else "medium" if score >= 1 else "low"
    return {
        "level": level,
        "escalate": level == "high",
        "score": score,
        "factors": factors,
        "new_sentiment": new_sentiment,
    }


# ---------------------------------------------------------------------------
# Risk-aware responder — a lean LlmAgent (no planner). Tone adapts to posture.
# ---------------------------------------------------------------------------

def _build_inbound_responder(after_agent_callback=None):
    from google.adk.agents import LlmAgent
    from core.model_config import get_model, ModelUseCase
    from ..runtime.callbacks import langfuse_model_cb

    return LlmAgent(
        name="inbound_responder",
        model=get_model(ModelUseCase.DRAFT_EMAIL),
        instruction=(
            "You draft the reply a CSM will review and send. It must be ready to send after a "
            "quick human check.\n\n"
            "CUSTOMER: {customer_name}\n\n"
            "THEIR MESSAGE:\n{task_summary}\n\n"
            "CLASSIFICATION (category / sentiment / complexity):\n{inbound_classification}\n\n"
            "Write a reply that directly addresses what they asked. Match the company voice in your "
            "context — warm, concrete, no fluff. Set clear expectations on what happens next.\n"
            "IF the sentiment is angry or frustrated: lead with genuine acknowledgement of their "
            "frustration, do not be defensive, and make the next step concrete and soon. Do NOT "
            "promise fixes or dates you can't back up.\n"
            "Output a subject and body."
        ),
        output_schema=SupportResponseOutput,
        output_key=INBOUND_RESPONSE_KEY,
        after_agent_callback=after_agent_callback,
        after_model_callback=langfuse_model_cb,
    )


# ---------------------------------------------------------------------------
# Persist — branches on risk posture (the "response package")
# ---------------------------------------------------------------------------

class PersistInbound(BaseAgent):
    """Write the drafted reply + surface a Need. The PACKAGE varies by risk posture:
    - low/medium  → draft_response_ready Need (review-and-send), priority 8
    - high        → escalation Need (priority 2) + the draft + a flag observation,
                    AND enqueue a Lane-2 risk_save_play so the relationship gets worked."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        workspace_id = state.get(KEY_WORKSPACE_ID)
        customer_id = state.get(KEY_CUSTOMER_ID)
        customer_name = state.get(KEY_CUSTOMER_NAME) or "the customer"
        payload = state.get(KEY_PAYLOAD) or {}
        run_id = state.get(KEY_RUN_ID)
        classification = _parse(state, INBOUND_CLASS_KEY) or {}
        reply = _parse(state, INBOUND_RESPONSE_KEY)

        if not reply or not workspace_id or not customer_id:
            yield _event(self.name, "No inbound reply to persist; skipping.")
            return

        # Skip FYI/thank-you messages that don't require a reply or action.
        if not classification.get("is_actionable", True):
            logger.info("inbound_not_actionable", customer_id=customer_id,
                        category=classification.get("category"), sentiment=classification.get("sentiment"))
            yield _event(self.name, f"Message is not actionable — skipping Need/Draft creation.")
            return

        # Compute risk HERE (last stage) — the classifier's output_key is reliably applied
        # by now, unlike an immediately-following sub-agent which would read it stale.
        new_sentiment = classification.get("sentiment", "neutral")
        posture = await assess_inbound_risk(workspace_id, customer_id, new_sentiment)
        state[RISK_POSTURE_KEY] = posture
        logger.info("inbound_risk_assessed", customer_id=customer_id, level=posture["level"],
                    score=posture["score"], escalate=posture["escalate"], new_sentiment=new_sentiment)

        summary = classification.get("summary") or "Inbound message"
        level = posture.get("level", "low")
        escalate = bool(posture.get("escalate"))
        source_event_id = payload.get("source_event_id")
        thread_id = payload.get("thread_id")

        if escalate:
            need_type = "escalation"
            priority = 2
            lede = f"High-risk inbound — {summary}. A drafted reply is ready; the account also needs a save play."
        else:
            need_type = "draft_response_ready"
            priority = 8
            lede = f"{summary}. A drafted reply is ready for your review."

        # Lane 1 is standalone — no AgentRun row exists for this run_id, so we must NOT
        # link it (need.agent_run_id is a FK). run_id is for tracing/logging only here.
        need_id = await artifacts.surface_need(
            workspace_id, customer_id,
            need_type=need_type,
            headline=f"{customer_name}: {summary}",
            lede=lede,
            reasoning=f"risk={level} ({', '.join(posture.get('factors', [])) or 'no risk factors'})",
            source_event_id=source_event_id,
            agent_run_id=None,
            priority_rank=priority,
            thread_id=thread_id,
        )
        state[STATE_NEED_ID] = need_id

        draft_id = await artifacts.create_draft_response(
            workspace_id, customer_id,
            body=reply.get("body", ""),
            subject=reply.get("subject"),
            thread_id=thread_id,
            surfaced_in_need_id=need_id,
        )
        state[STATE_DRAFT_ID] = draft_id

        if escalate:
            state[STATE_ESCALATED] = True
            await artifacts.record_observation(
                workspace_id, customer_id,
                text=f"Inbound flagged HIGH risk ({', '.join(posture.get('factors', []))}). "
                     f"Drafted a reply and handing off a save play.",
                agent_run_id=None, kind="observed",
            )
            # Hand off to Lane 2 — enqueue a worker task that will run risk_save_play.
            # The play runs LATER (on the next drain), so it won't appear in this trace.
            # We emit a span here so the handoff is visible and links to the queued task.
            try:
                from ..queue.repository import AgentTaskRepository
                from core.telemetry import get_langfuse

                # Idempotency: if this customer already has an active task queued, don't
                # pile on another. The worker handles the account holistically when it runs.
                existing = await get_dataconnect_client().execute_query(
                    "GetActiveTasksForCustomer",
                    {"workspaceId": workspace_id, "customerId": customer_id},
                )
                if existing.get("agentTasks"):
                    logger.info("inbound_handoff_skipped_active_task",
                                customer_id=customer_id,
                                existing_task_id=existing["agentTasks"][0].get("id"))
                    raise _SkipHandoff()

                handoff_payload = {
                    "need_type": "renewal_at_risk",
                    "summary": f"Inbound from {customer_name} flagged high-risk: {summary}",
                    "source_event_id": source_event_id,
                    "from_inbound_lane": True,
                }
                lf = get_langfuse()
                if lf:
                    with lf.start_as_current_observation(
                        name="handoff:risk_save_play", as_type="span",
                        input={"customer": customer_name, "reason": posture.get("factors", [])},
                    ) as span:
                        task_id = await AgentTaskRepository(workspace_id).enqueue(
                            "triage_signal", customer_id=customer_id, trigger_type="signal",
                            priority=10, payload=handoff_payload,
                        )
                        try:
                            span.update(output={"enqueued_task_id": task_id,
                                                "note": "risk_save_play will run on next drain"})
                        except Exception:
                            pass
                else:
                    await AgentTaskRepository(workspace_id).enqueue(
                        "triage_signal", customer_id=customer_id, trigger_type="signal",
                        priority=10, payload=handoff_payload,
                    )
            except _SkipHandoff:
                pass  # already an active task for this customer — intentional no-op
            except Exception as e:
                logger.warning("inbound_escalation_enqueue_failed", customer_id=customer_id, error=str(e))

        logger.info("inbound_persisted", need_id=need_id, draft_id=draft_id,
                    need_type=need_type, level=level, escalate=escalate)

        # Emit results as a committed state_delta. Direct `state[...] =` writes mutate only
        # the in-memory session and are NOT persisted — the entry runner's fresh get_session
        # (used to build the result) would miss them. A state_delta on the event IS committed.
        text = (f"Drafted a reply for {customer_name} ({need_type}, risk={level})"
                + (" + handed off a save play." if escalate else "."))
        yield Event(
            author=self.name,
            content=types.Content(role="model", parts=[types.Part(text=text)]),
            actions=EventActions(state_delta={
                RISK_POSTURE_KEY: posture,
                STATE_NEED_ID: need_id,
                STATE_DRAFT_ID: draft_id,
                STATE_ESCALATED: escalate,
            }),
        )


def build_support_triage_play(workspace_id: str, customer_id: str, after_agent_callback=None) -> SequentialAgent:
    """Compose the light inbound-support lane for one account."""
    return SequentialAgent(
        name="support_triage_play",
        description=(
            "The light, high-volume lane for ordinary inbound support: classify the message, "
            "assess account risk deterministically, draft a reply, and surface it. Escalates to "
            "a full save play only when the customer is at risk or the message is angry."
        ),
        sub_agents=[
            build_inbound_classifier(after_agent_callback=after_agent_callback),
            _build_inbound_responder(after_agent_callback=after_agent_callback),
            PersistInbound(name="persist_inbound", after_agent_callback=after_agent_callback),
        ],
    )


async def run_inbound_support(
    *,
    workspace_id: str,
    customer_id: str,
    customer_name: str,
    subject: str,
    body: str,
    run_id: str,
    source_event_id: str | None = None,
    thread_id: str | None = None,
) -> dict:
    """Entry point: run the light lane for one inbound message, return a result summary.
    Standalone (no queue) — Lane 1 never instantiates the orchestrator worker."""
    import uuid as _uuid
    from ..runtime.runner import APP_NAME, build_runner, default_run_config
    from ..runtime.services import get_session_service
    from ..runtime.state import initial_state

    event_id = source_event_id or f"inbound:{_uuid.uuid4().hex[:12]}"

    # Re-engagement: receiving this message means the customer is no longer DARK at the
    # ACCOUNT level. Supersede account-silence signals (going_dark/cadence) and resolve
    # open going_dark needs BEFORE risk assessment, so a friendly question from a
    # previously-quiet account isn't treated as a churn signal.
    #
    # Tiered contact-reset (ENGAGEMENT_HEALTH_MODEL.md): this intentionally does NOT
    # clear the derived `engagement` signal, which encodes champion-silence and
    # responsiveness decay. A non-champion reply resets account-total-silence but must
    # not clear champion-specific risk — that only relaxes when the champion themselves
    # re-engages (their lastInteractionAt updates, and the next sweep heartbeat lowers
    # the contact-level penalty). Other risk (sentiment, renewal, escalations) also persists.
    try:
        dc = get_dataconnect_client()
        await dc.execute_mutation(
            "SupersedeAbsenceSignalsForCustomer",
            {"workspaceId": workspace_id, "customerId": customer_id},
        )
        await dc.execute_mutation(
            "ResolveGoingDarkNeedsForCustomer",
            {"workspaceId": workspace_id, "customerId": customer_id},
        )
    except Exception as e:
        logger.warning("reengagement_update_failed", customer_id=customer_id, error=str(e))

    play = build_support_triage_play(workspace_id, customer_id)

    state = initial_state(
        run_id=run_id, task_id="inbound", workspace_id=workspace_id,
        customer_id=customer_id, customer_name=customer_name, trigger_type="signal",
        payload={"source_event_id": event_id, "thread_id": thread_id},
    )
    state["task_summary"] = f"Subject: {subject}\n\n{body}" if subject else body

    session_service = get_session_service()
    session = await session_service.create_session(app_name=APP_NAME, user_id=workspace_id, state=state)
    runner = build_runner(play)
    msg = types.Content(role="user", parts=[types.Part(text=f"Process this inbound message for {customer_name}.")])
    async for _e in runner.run_async(
        user_id=workspace_id, session_id=session.id, new_message=msg, run_config=default_run_config()
    ):
        pass

    final = await session_service.get_session(app_name=APP_NAME, user_id=workspace_id, session_id=session.id)
    fstate = final.state if final else session.state
    classification = _parse(fstate, INBOUND_CLASS_KEY) or {}
    posture = _parse(fstate, RISK_POSTURE_KEY) or {}
    reply = _parse(fstate, INBOUND_RESPONSE_KEY) or {}

    return {
        "customer_name": customer_name,
        "category": classification.get("category"),
        "sentiment": classification.get("sentiment"),
        "complexity": classification.get("complexity"),
        "summary": classification.get("summary"),
        "risk_level": posture.get("level"),
        "escalated": bool(fstate.get(STATE_ESCALATED)),
        "risk_factors": posture.get("factors", []),
        "need_id": fstate.get(STATE_NEED_ID),
        "draft_id": fstate.get(STATE_DRAFT_ID),
        "draft_subject": reply.get("subject"),
        "draft_preview": (reply.get("body") or "")[:200],
    }

"""
Risk/Save play — deterministic SequentialAgent (the demo's supporting cast).

  Researcher (LLM)  → research_summary
  RiskStrategist (LLM, output_schema) → risk_save (structured)
  PersistRiskPlay (deterministic) → RiskBrief + RiskPlayStep rows; state[risk_brief_id]
  SurfaceRiskNeed (deterministic) → Need row; state[need_id]
  RiskOutreach (LLM, output_schema) → risk_outreach (re-engagement email)
  PersistRiskDraft (deterministic) → DraftResponse on an email thread; state[risk_draft_id]

Autonomy lives in the worker (which DECIDES to run this); the play itself is a
reliable workflow. The two persistence stages are deterministic Python (no LLM
misfire) so the artifacts are guaranteed when the play runs.
"""

import json
from typing import Any, AsyncGenerator

from google.adk.agents import BaseAgent, SequentialAgent, LoopAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

from core.logging import get_logger

# Reused read-only Voice lookup (import, never modify handoff_auto).
from agents.handoff_auto.tools.context import get_handbook_guide as _get_handbook_guide

from .. import artifacts
from ..runtime.callbacks import before_agent_callback
from ..runtime.state import (
    KEY_WORKSPACE_ID,
    KEY_CUSTOMER_ID,
    KEY_CUSTOMER_NAME,
    KEY_RUN_ID,
    KEY_PAYLOAD,
)
from ..specialists import build_researcher, build_risk_strategist, build_risk_outreach, build_critic
from ..specialists.risk_strategist import RISK_SAVE_KEY, RISK_OUTREACH_KEY
from ..specialists.critic import CRITIC_KEY

logger = get_logger("RiskSavePlay")

STATE_BRIEF_ID = "risk_brief_id"
STATE_BRIEF_REUSED = "risk_brief_reused"
STATE_NEED_ID = "need_id"
STATE_DRAFT_ID = "risk_draft_id"
STATE_THREAD_ID = "risk_draft_thread_id"
STATE_CRITIC_FEEDBACK = "critic_feedback"
STATE_QUALITY = "quality_assessment_json"


def _risk_save(state: Any) -> dict | None:
    """Normalize the strategist output (dict | JSON str | pydantic) to a dict."""
    rs = state.get(RISK_SAVE_KEY)
    if rs is None:
        return None
    if isinstance(rs, str):
        try:
            return json.loads(rs)
        except json.JSONDecodeError:
            return None
    if isinstance(rs, dict):
        return rs
    if hasattr(rs, "model_dump"):
        return rs.model_dump()
    return None


def _event(author: str, text: str, state_delta: dict | None = None) -> Event:
    kwargs = {"author": author, "content": types.Content(role="model", parts=[types.Part(text=text)])}
    if state_delta:
        # Only set actions when we have a delta — Event rejects actions=None
        # (it defaults to a fresh EventActions()).
        kwargs["actions"] = EventActions(state_delta=state_delta)
    return Event(**kwargs)


async def _load_risk_playbook(workspace_id: str) -> str:
    """Fetch the workspace's RISK playbook and format its steps as markdown.
    Returns '(none)' when the workspace hasn't formalized a risk play (additive fallback)."""
    from db.dataconnect_client import get_dataconnect_client
    try:
        res = await get_dataconnect_client().execute_query(
            "GetRiskPlaybook", {"workspaceId": workspace_id}
        )
    except Exception as e:
        logger.warning("load_risk_playbook_failed", error=str(e))
        return "(none)"
    pbs = res.get("playbooks", [])
    if not pbs:
        return "(none)"
    pb = pbs[0]
    steps = pb.get("playbookMilestones_on_playbook") or []
    if not steps:
        return "(none)"
    lines = [f"Playbook: {pb.get('name','(unnamed)')}"]
    if pb.get("fitNote"):
        lines.append(f"When to use: {pb['fitNote']}")
    for i, s in enumerate(steps, 1):
        rationale = f" — {s['description']}" if s.get("description") else ""
        lines.append(f"{i}. {s.get('title','')}{rationale}")
    return "\n".join(lines)


def _event_id(state, customer_id: str) -> str:
    """The triggering event's id from the task payload — the idempotency/dedupe key.
    Falls back to a per-customer marker if a payload somehow lacks one."""
    payload = state.get(KEY_PAYLOAD) or {}
    return payload.get("source_event_id") or f"auto:{customer_id}"


# Need type surfaced by THIS play (the risk/save play). Future plays define their own.
RISK_NEED_TYPE = "renewal_at_risk"


class LoadRiskContext(BaseAgent):
    """Deterministic pre-load: the workspace's risk playbook + the going-dark Voice
    into session state, so the (tool-less, output_schema) risk strategist can template
    them. Additive — sets '(none)' / default guidance when nothing is customized."""

    async def _run_async_impl(self, ctx: InvocationContext):
        state = ctx.session.state
        workspace_id = state.get(KEY_WORKSPACE_ID)
        risk_playbook = "(none)"
        voice_guide = "(use a calm, concrete, customer-first tone)"
        if workspace_id:
            risk_playbook = await _load_risk_playbook(workspace_id)
            try:
                guide = await _get_handbook_guide(workspace_id, "going dark")
                voice_guide = guide.get("guide_content") or voice_guide
            except Exception as e:
                logger.warning("load_voice_guide_failed", error=str(e))
        has_pb = risk_playbook != "(none)"
        logger.info("risk_context_loaded", has_playbook=has_pb)
        yield _event(
            self.name,
            ("Loaded workspace risk playbook + voice." if has_pb
             else "No workspace risk playbook; will design from best practices."),
            state_delta={
                "risk_playbook": risk_playbook,
                "voice_guide": voice_guide,
                # Seed so the strategist's {critic_feedback} templating resolves on pass 1.
                STATE_CRITIC_FEEDBACK: "(first pass — no prior feedback)",
            },
        )


class CriticGate(BaseAgent):
    """Loop controller: read the Critic's verdict, stash the quality assessment, and
    either escalate (stop the LoopAgent) when approved, or feed `feedback` back to the
    strategist for one more pass. max_iterations on the LoopAgent is the hard cap."""

    async def _run_async_impl(self, ctx: InvocationContext):
        state = ctx.session.state
        verdict = state.get(CRITIC_KEY)
        if isinstance(verdict, str):
            try:
                verdict = json.loads(verdict)
            except json.JSONDecodeError:
                verdict = None
        elif hasattr(verdict, "model_dump"):
            verdict = verdict.model_dump()

        # Respect the critic's explicit verdict — never override a veto on score alone.
        approved = bool(verdict and verdict.get("approved"))
        score = (verdict or {}).get("score")
        feedback = (verdict or {}).get("feedback") or "(approved)"
        quality = json.dumps(verdict) if verdict else "{}"

        delta = {STATE_QUALITY: quality}
        if not approved:
            delta[STATE_CRITIC_FEEDBACK] = feedback

        logger.info("critic_gate", approved=approved, score=score)
        msg = (f"Critic approved the play (score {score})." if approved
               else f"Critic requested revision (score {score}): {feedback[:120]}")
        # Escalate stops the LoopAgent immediately when approved.
        actions = EventActions(state_delta=delta, escalate=True) if approved \
            else EventActions(state_delta=delta)
        yield Event(
            author=self.name,
            content=types.Content(role="model", parts=[types.Part(text=msg)]),
            actions=actions,
        )


class PersistRiskPlay(BaseAgent):
    """Write RiskBrief + RiskPlayStep rows from the strategist's structured output."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        rs = _risk_save(state)
        workspace_id = state.get(KEY_WORKSPACE_ID)
        customer_id = state.get(KEY_CUSTOMER_ID)
        if not rs or not workspace_id or not customer_id:
            yield _event(self.name, "No risk assessment to persist; skipping.")
            return

        # Idempotency keyed on the triggering EVENT (not the customer): reuse only a
        # brief written for THIS event (e.g. the play dispatched twice in one run).
        # A genuinely new event always gets a fresh brief.
        event_id = _event_id(state, customer_id)
        from db.dataconnect_client import get_dataconnect_client
        existing = (await get_dataconnect_client().execute_query(
            "GetRiskBriefByEvent", {"workspaceId": workspace_id, "inputsHash": event_id}
        )).get("riskBriefs", [])
        if existing:
            state[STATE_BRIEF_ID] = existing[0]["id"]
            state[STATE_BRIEF_REUSED] = True  # signal PersistRiskDraft to skip re-drafting
            yield _event(self.name, "Risk brief already exists for this event; reusing it.")
            return

        brief_id = await artifacts.create_risk_brief(
            workspace_id, customer_id,
            what_changed=rs.get("what_changed", ""),
            evidence_text=rs.get("evidence_text"),
            play_summary=rs.get("play_summary"),
            event_id=event_id,
        )
        if not brief_id:
            # Insert returned no id — do NOT write steps with a null FK, and don't
            # report success. The DB-gated backstop will see no brief and retry.
            logger.error("risk_brief_insert_no_id", customer_id=customer_id)
            yield _event(self.name, "Could not persist the risk brief (no id returned); skipping steps.")
            return

        steps = rs.get("steps") or []
        for i, step in enumerate(steps):
            await artifacts.add_risk_step(brief_id, step.get("label", ""), step.get("rationale"), i)

        state[STATE_BRIEF_ID] = brief_id
        logger.info("risk_play_persisted", brief_id=brief_id, steps=len(steps))
        yield _event(self.name, f"Wrote risk brief + {len(steps)} save-play steps.")


class SurfaceRiskNeed(BaseAgent):
    """Surface the save play as a Need in the Today queue (carries sourceEventId)."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        rs = _risk_save(state)
        workspace_id = state.get(KEY_WORKSPACE_ID)
        customer_id = state.get(KEY_CUSTOMER_ID)
        customer_name = state.get(KEY_CUSTOMER_NAME) or "This customer"
        payload = state.get(KEY_PAYLOAD) or {}
        if not rs or not workspace_id or not customer_id:
            yield _event(self.name, "No risk assessment to surface; skipping.")
            return

        # Idempotency is handled by `surface_need` below, which dedupes per
        # (source_event_id + need_type) — so a risk overlay (renewal_at_risk) and a primary
        # support Need (urgent_support) coexist on the SAME event instead of one masking the other.
        risk_level = rs.get("risk_level", "high")
        # Fold the critic's quality score into the reasoning (self-eval visible to CSM).
        quality_note = ""
        q = state.get(STATE_QUALITY)
        if q:
            try:
                qd = json.loads(q) if isinstance(q, str) else q
                if qd.get("score"):
                    quality_note = f" [self-review: {qd['score']}/5]"
            except Exception:
                pass
        # The producer can hint the need framing (going_dark, frustrated_signal, …) so the
        # Today queue reflects the actual trigger; default to renewal_at_risk.
        # Only accept risk-appropriate types from payload — non-risk types (e.g. urgent_support
        # from a support_outage event) must not leak into the risk play's Need row.
        _RISK_NEED_TYPES = {
            "going_dark", "renewal_at_risk", "frustrated_signal",
            "open_commitment_overdue", "approaching_renewal",
            "champion_departed", "onboarding_behind",
        }
        raw_type = payload.get("need_type")
        need_type = raw_type if raw_type in _RISK_NEED_TYPES else RISK_NEED_TYPE
        summary = rs.get("play_summary") or "save play ready"
        need_id = await artifacts.surface_need(
            workspace_id, customer_id,
            need_type=need_type,
            headline=f"{customer_name}: {summary}",
            lede=rs.get("what_changed") or "Review the recommended save play.",
            reasoning=f"{rs.get('what_changed','')} {rs.get('evidence_text','')}{quality_note}".strip(),
            source_event_id=payload.get("source_event_id"),
            agent_run_id=state.get(KEY_RUN_ID),
            priority_rank=3 if risk_level == "high" else 6,
            thread_id=payload.get("thread_id"),
        )
        state[STATE_NEED_ID] = need_id
        logger.info("risk_need_surfaced", need_id=need_id, risk_level=risk_level)
        yield _event(self.name, "Surfaced a renewal-at-risk Need in the Today queue.")


def _outreach(state: Any) -> dict | None:
    """Normalize the outreach drafter output (dict | JSON str | pydantic) to a dict."""
    v = state.get(RISK_OUTREACH_KEY)
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


class PersistRiskDraft(BaseAgent):
    """Persist the re-engagement email as a real DraftResponse on an email thread, linked
    to the risk Need — the artifact the CSM reviews at the HITL pause (same pattern as the
    support play). Customer comms are EMAIL: a customer-facing Slack message would need
    Slack Connect we don't have."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        # Skip when we reused an existing brief (we've already drafted on a prior pass).
        if state.get(STATE_BRIEF_REUSED):
            yield _event(self.name, "Outreach already drafted for this event; skipping.")
            return
        draft = _outreach(state)
        workspace_id = state.get(KEY_WORKSPACE_ID)
        customer_id = state.get(KEY_CUSTOMER_ID)
        customer_name = state.get(KEY_CUSTOMER_NAME) or "this customer"
        need_id = state.get(STATE_NEED_ID)
        if not draft or not draft.get("body") or not workspace_id or not customer_id:
            yield _event(self.name, "No outreach draft to persist; skipping.")
            return

        # Deterministic email outreach thread (idempotent across retries). Going-dark has no
        # inbound thread to reply to, so we open the re-engagement thread the way the support
        # play reuses its inbound one. Non-fatal: the brief + Need are already persisted, so a
        # draft hiccup must NOT fail the whole run (the HITL pause then shows brief-only).
        import uuid as _uuid
        thread_id = str(_uuid.uuid5(
            _uuid.NAMESPACE_URL, f"risk-outreach:{workspace_id}:{customer_id}"
        ))
        from db.dataconnect_client import get_dataconnect_client
        dc = get_dataconnect_client()
        try:
            thread_id_for_draft: str | None = thread_id
            try:
                await dc.execute_mutation("CreateThreadWithId", {
                    "id": thread_id, "workspaceId": workspace_id, "customerId": customer_id,
                    "needId": need_id, "subject": draft.get("subject") or f"Re-engaging {customer_name}",
                    "channel": "email", "threadType": "customer", "status": "open",
                    "externalThreadId": f"risk-outreach:{customer_id}",
                })
            except Exception as e:
                # A duplicate id on re-run is fine (the thread already exists). For any other
                # failure, confirm existence — and if it truly isn't there, drop the thread link
                # so the draft can't violate the FK (it still links to the Need).
                exists = False
                try:
                    exists = bool((await dc.execute_query(
                        "GetThreadForDraft", {"id": thread_id})).get("thread"))
                except Exception:
                    exists = False
                if exists:
                    logger.info("risk_outreach_thread_exists", thread_id=thread_id)
                else:
                    logger.warning("risk_outreach_thread_create_failed", thread_id=thread_id, error=str(e))
                    thread_id_for_draft = None

            # Complete the REVERSE link (Need.thread). CreateThreadWithId only set Thread.need (the
            # forward FK); the conversation's "needs on this thread" reads Need.thread, so without
            # this the thread shows as not linked to a need.
            if need_id and thread_id_for_draft:
                try:
                    await dc.execute_mutation(
                        "LinkNeedToThread", {"needId": need_id, "threadId": thread_id_for_draft})
                except Exception as e:
                    logger.info("risk_outreach_need_link_skipped", error=str(e))

            # Sidekick's "why I opened this" — an internal note on the thread so the conversation
            # doubles as the reasoning surface (the brief also stays on the customer record). Placed
            # before the draft so the thread reads: reasoning → drafted reply.
            rs = _risk_save(state) or {}
            if thread_id_for_draft:
                note_lines = []
                if rs.get("what_changed"):
                    note_lines.append(rs["what_changed"].strip())
                if rs.get("evidence_text"):
                    note_lines.append(f"Evidence: {rs['evidence_text'].strip()}")
                steps = rs.get("steps") or []
                if steps:
                    note_lines.append("Save play:\n" + "\n".join(
                        f"{i + 1}. {s.get('label', '')}" for i, s in enumerate(steps)))
                if note_lines:
                    from datetime import datetime, timezone
                    note_id = str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"risk-outreach-note:{workspace_id}:{customer_id}"))
                    try:
                        await dc.execute_mutation("CreateInteractionFromEvent", {
                            "id": note_id, "workspaceId": workspace_id, "customerId": customer_id,
                            "threadId": thread_id_for_draft, "channel": "note", "direction": "internal",
                            "senderName": "Sidekick", "stakeholderId": None,
                            "subject": "Why I opened this need",
                            "body": "Why I opened this need — " + "\n\n".join(note_lines),
                            "sourceEventId": f"risk-outreach-note:{customer_id}",
                            "occurredAt": datetime.now(timezone.utc).isoformat(),
                            "interactionSource": "orchestrator",
                        })
                    except Exception as e:  # non-fatal (e.g. duplicate on re-run)
                        logger.info("risk_outreach_note_skipped", error=str(e))

            draft_id = await artifacts.create_draft_response(
                workspace_id, customer_id,
                body=draft.get("body", ""),
                subject=draft.get("subject"),
                thread_id=thread_id_for_draft,
                surfaced_in_need_id=need_id,
            )
            state[STATE_DRAFT_ID] = draft_id
            state[STATE_THREAD_ID] = thread_id_for_draft
            logger.info("risk_outreach_persisted", draft_id=draft_id,
                        thread_id=thread_id_for_draft, need_id=need_id)
        except Exception as e:
            logger.exception("risk_outreach_persist_failed", customer_id=customer_id, error=str(e))
            yield _event(self.name, "Could not persist the outreach draft (non-fatal); continuing.")
            return
        yield _event(self.name, f"Drafted a re-engagement email to {customer_name} for review.")


def build_risk_save_play(workspace_id: str, customer_id: str, notion_token: str | None = None, after_agent_callback=None) -> SequentialAgent:
    """Compose the Risk/Save play for one account. `after_agent_callback` (optional)
    streams each stage's completion to Firestore for visible stage handoffs."""
    # Plan→Critic revise loop (ADK LoopAgent): the strategist proposes, the critic
    # judges; the gate escalates to stop when approved, else one revision pass.
    plan_critic = LoopAgent(
        name="plan_critic",
        max_iterations=2,
        sub_agents=[
            build_risk_strategist(after_agent_callback=after_agent_callback),
            build_critic(after_agent_callback=after_agent_callback),
            CriticGate(name="critic_gate", after_agent_callback=after_agent_callback),
        ],
    )
    return SequentialAgent(
        name="risk_save_play",
        before_agent_callback=before_agent_callback,  # stream the play root at start (reveals the Lab subtree immediately)
        description=(
            "Run when the account is at churn or renewal risk: gone dark, stalled onboarding, "
            "frustrated stakeholder, or escalating frustration. Produces a Risk Brief with a "
            "save strategy and action steps, surfaces a renewal_at_risk Need in the CSM's queue, "
            "and drafts a re-engagement email for CSM review."
        ),
        sub_agents=[
            LoadRiskContext(name="load_risk_context", after_agent_callback=after_agent_callback),
            build_researcher(workspace_id, customer_id, notion_token=notion_token, after_agent_callback=after_agent_callback),
            plan_critic,
            PersistRiskPlay(name="persist_risk_play", after_agent_callback=after_agent_callback),
            SurfaceRiskNeed(name="surface_risk_need", after_agent_callback=after_agent_callback),
            build_risk_outreach(after_agent_callback=after_agent_callback),
            PersistRiskDraft(name="persist_risk_draft", after_agent_callback=after_agent_callback),
        ],
    )

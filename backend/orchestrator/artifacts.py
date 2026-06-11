"""
Orchestrator-owned DB writes (real rows the UI renders — zero mocks).

Kept separate from `agents/handoff_auto/` so the worker/plays never depend on that
agent's HITL side-channel. Reuses existing DataConnect mutations (incl.
`CreateNeedWithId`, which already accepts `sourceEventId` — letting the demo reset
delete exactly what it created). All writes are idempotent-friendly and best-effort
on the Firestore notify.
"""

import hashlib
import uuid
from typing import Any

from core.logging import get_logger
from db.dataconnect_client import get_dataconnect_client

logger = get_logger("OrchestratorArtifacts")


def inputs_hash(*parts: str) -> str:
    return hashlib.sha256("|".join(p or "" for p in parts).encode()).hexdigest()[:32]


async def create_risk_brief(
    workspace_id: str,
    customer_id: str,
    *,
    what_changed: str,
    evidence_text: str | None,
    play_summary: str | None,
    event_id: str | None = None,
) -> str | None:
    """Write a RiskBrief row. `inputsHash` carries the triggering event id so
    idempotency is per-event (a new going-dark event makes a new brief even if the
    customer has an old one). Returns brief id."""
    dc = get_dataconnect_client()
    res = await dc.execute_mutation(
        "CreateRiskBrief",
        {
            "workspaceId": workspace_id,
            "customerId": customer_id,
            "whatChanged": what_changed,
            "evidenceText": evidence_text,
            "play": play_summary,
            "inputsHash": event_id or inputs_hash(workspace_id, customer_id, what_changed),
        },
    )
    brief_id = (res.get("riskBrief_insert") or {}).get("id")
    logger.info("risk_brief_created", brief_id=brief_id, customer_id=customer_id)
    return brief_id


async def add_risk_step(brief_id: str, label: str, rationale: str | None, sort_order: int) -> None:
    dc = get_dataconnect_client()
    await dc.execute_mutation(
        "CreateRiskPlayStep",
        {"briefId": brief_id, "label": label, "rationale": rationale, "sortOrder": sort_order},
    )


async def surface_need(
    workspace_id: str,
    customer_id: str,
    *,
    need_type: str,
    headline: str,
    lede: str,
    reasoning: str,
    source_event_id: str | None,
    agent_run_id: str | None,
    priority_rank: int = 5,
    thread_id: str | None = None,
) -> str:
    """Surface a Need in the Today queue (real row + Firestore notify).

    Dedupe is per **(source_event_id + need_type)**: multiple plays can surface
    DIFFERENT-typed Needs for the same event (fan-out — e.g. a support draft AND a
    renewal save on one email), but the same type won't duplicate on re-run. Links
    `Need.thread` when `thread_id` is given (so the conversation screen shows it).
    """
    dc = get_dataconnect_client()

    # Per-(event, type) dedupe.
    if source_event_id and dc.has_operation("GetNeedsBySourceEvent"):
        existing = (await dc.execute_query(
            "GetNeedsBySourceEvent", {"workspaceId": workspace_id, "sourceEventId": source_event_id}
        )).get("needs", [])
        for n in existing:
            if n.get("type") == need_type:
                logger.info("need_dedupe_reuse", need_id=n["id"], need_type=need_type)
                return n["id"]

    need_id = str(uuid.uuid4())
    await dc.execute_mutation(
        "CreateNeedWithId",
        {
            "id": need_id,
            "workspaceId": workspace_id,
            "customerId": customer_id,
            "type": need_type,
            "headline": headline,
            "lede": lede,
            "priorityRank": priority_rank,
            "agentReasoning": reasoning,
            "handbookVersionId": None,
            "agentRunId": agent_run_id,
            "sourceEventId": source_event_id,
            "threadId": thread_id,
        },
    )
    # Close the bidirectional link so Thread.needId is also set (UI navigates both ways).
    if thread_id and dc.has_operation("LinkThreadToNeed"):
        await dc.execute_mutation("LinkThreadToNeed", {"threadId": thread_id, "needId": need_id})
    logger.info("need_surfaced", need_id=need_id, customer_id=customer_id, need_type=need_type)
    try:
        from services.firestore_service import get_firestore_service
        await get_firestore_service().notify_need_created(
            workspace_id=workspace_id, need_id=need_id, need_type=need_type, customer_name=None,
        )
    except Exception as e:
        logger.warning("need_notify_failed", need_id=need_id, error=str(e))
    return need_id


# Back-compat alias (callers still pass need_type explicitly).
surface_risk_need = surface_need


async def record_observation(
    workspace_id: str,
    customer_id: str,
    *,
    text: str,
    agent_run_id: str | None,
    kind: str = "observed",
    timestamp_label: str | None = None,
) -> str | None:
    """Write a SidekickItem (RightRail activity). kind: observed | tip."""
    dc = get_dataconnect_client()
    res = await dc.execute_mutation(
        "CreateSidekickItem",
        {
            "workspaceId": workspace_id,
            "customerId": customer_id,
            "type": kind,
            "text": text,
            "agentRunId": agent_run_id,
            "timestampLabel": timestamp_label,
            # unused fields explicitly null
            "question": None, "why": None, "isBlocking": None, "task": None,
            "step": None, "stepNum": None, "totalSteps": None, "needId": None,
            "resolution": None, "resolvedByUserId": None, "resolvedAt": None,
        },
    )
    item_id = (res.get("sidekickItem_insert") or {}).get("id")
    logger.info("observation_recorded", item_id=item_id, customer_id=customer_id, kind=kind)
    return item_id


async def create_draft_response(
    workspace_id: str,
    customer_id: str,
    *,
    body: str,
    subject: str | None = None,
    thread_id: str | None = None,
    surfaced_in_need_id: str | None = None,
    citations: str | None = None,
) -> str | None:
    """Write a DraftResponse (status pending_review). Links the thread (when known) and
    the surfacing Need so it renders on both the thread and need screens. `citations`
    (the 'vector preview') stays None until the grounding layer populates it."""
    dc = get_dataconnect_client()
    res = await dc.execute_mutation(
        "CreateDraftResponse",
        {
            "workspaceId": workspace_id,
            "customerId": customer_id,
            "threadId": thread_id,
            "subject": subject,
            "body": body,
            "citations": citations,
            "surfacedInNeedId": surfaced_in_need_id,
            "model": "orchestrator-support",
            "promptVersion": "support-v1",
            "handbookVersionId": "00000000-0000-0000-0000-000000000000",
        },
    )
    draft_id = (res.get("draftResponse_insert") or {}).get("id")
    logger.info("draft_response_created", draft_id=draft_id, customer_id=customer_id, has_thread=bool(thread_id))
    return draft_id


# Keywords that identify the "send the outreach" save-play step, auto-completed when a draft on
# the play's thread is sent (so the CSM never has to check that box manually).
_OUTREACH_STEP_KEYWORDS = (
    "outreach", "re-engag", "reengage", "reach out", "reach-out", "email", "send",
    "message", "contact", "follow up", "follow-up", "draft",
)

# When a save outreach goes out to a still-dark account, clear its Need from the Today queue but
# let it re-surface this many days out if they never reply. Shared by the Sidekick-approve path
# (worker) and the conversation-send path (here). A starting floor — can flex on account factors.
SAVE_RESURFACE_DAYS = 5


async def send_draft_response(
    thread_id: str | None = None,
    *,
    customer_id: str | None = None,
    workspace_id: str | None = None,
    edited_body: str | None = None,
    resurface_days: int | None = None,
) -> dict[str, Any] | None:
    """The single 'send a reviewed draft' action — used by both the UI Send button and the HITL
    'approve' resume. SIMULATES the send (no real email yet — not wired to Gmail/SMTP): posts the
    draft as an outbound interaction on its thread (so it shows as sent in the conversation), marks
    the draft sent, moves the surfaced Need to awaiting_customer (the save isn't done — ball's in
    the customer's court), and auto-completes the matching save-play step. The future real-email
    integration plugs in right here.

    Pass `thread_id` (UI knows the thread) OR `customer_id` + `workspace_id` (the HITL resume only
    has the customer — we look up the customer's pending draft → its thread, robust to thread-id
    formatting). Caller must run under owner impersonation; the dc client's per-op heuristic handles
    the USER/USER_ANON (auth.uid) vs NO_ACCESS mutation mix. Best-effort: each sub-step is non-fatal."""
    from datetime import datetime, timezone
    dc = get_dataconnect_client()

    # Resolve the thread from the customer's pending draft when no thread_id was given.
    if not thread_id and customer_id and workspace_id:
        rows = (await dc.execute_query(
            "GetPendingDraftForCustomer",
            {"workspaceId": workspace_id, "customerId": customer_id},
        )).get("draftResponses", [])
        if rows:
            thread_id = (rows[0].get("thread") or {}).get("id")
    if not thread_id:
        logger.info("send_draft_no_thread_resolved", customer_id=customer_id)
        return None

    thread = (await dc.execute_query("GetThreadForDraft", {"id": thread_id})).get("thread")
    if not thread:
        logger.info("send_draft_no_thread", thread_id=thread_id)
        return None
    workspace_id = (thread.get("workspace") or {}).get("id")
    customer_id = (thread.get("customer") or {}).get("id")
    channel = thread.get("channel") or "email"

    drafts = (await dc.execute_query("GetDraftResponse", {"threadId": thread_id})).get("draftResponses", [])
    draft = drafts[0] if drafts else None
    if not draft or not workspace_id or not customer_id:
        logger.info("send_draft_no_pending_draft", thread_id=thread_id)
        return None
    draft_id = draft["id"]
    body = (edited_body or draft.get("editedBody") or draft.get("body") or "").strip()
    subject = draft.get("subject")
    need_id = (draft.get("surfacedInNeed") or {}).get("id")

    # 1. post the email as an outbound interaction → shows as "sent" in the thread timeline.
    try:
        await dc.execute_mutation("CreateInteractionFromEvent", {
            "id": str(uuid.uuid4()), "workspaceId": workspace_id, "customerId": customer_id,
            "threadId": thread_id, "channel": channel, "direction": "us", "senderName": None,
            "stakeholderId": None, "subject": subject, "body": body,
            "sourceEventId": f"sent:{draft_id}",
            "occurredAt": datetime.now(timezone.utc).isoformat(), "interactionSource": "sent",
        })
    except Exception as e:
        logger.warning("send_draft_interaction_failed", thread_id=thread_id, error=str(e))

    # 2. mark the draft sent.
    try:
        await dc.execute_mutation("MarkDraftSent", {"id": draft_id})
    except Exception as e:
        logger.warning("send_draft_mark_failed", draft_id=draft_id, error=str(e))

    # 2b. detect an open orchestrator save decision (the approve/counter/hold HITL) still parked on
    #     this Need's run. Sending from the conversation IS that approval — so this is a "save" send
    #     (clears the queue with a re-surface floor) and the parked decision must be closed below.
    #     The pending-draft guard already blocks an actual second send; this just clears the UI.
    save_decision = None
    if need_id:
        try:
            res = await dc.execute_query("GetSaveDecisionForNeed", {"needId": need_id})
            run = ((res.get("need") or {}).get("agentRun")) or {}
            blocking = run.get("blockingNeed") or {}
            if (run.get("status") in ("waiting_for_input", "resuming")
                    and blocking.get("type") == "sidekick_question"
                    and not blocking.get("resolvedAt")):
                save_decision = {"run_id": run.get("id"), "decision_need_id": blocking["id"]}
        except Exception as e:
            logger.warning("send_draft_decision_lookup_failed", need_id=need_id, error=str(e))

    # 3. the Need is now awaiting the customer (not resolved — the save isn't done). When this is a
    #    save send (explicit resurface_days, or a detected open save decision), also snooze it off
    #    the Today queue until the floor: we did the thing, so it shouldn't sit in "what to do now",
    #    but it reappears later if they never reply. A plain UI reply (no save) just flips status.
    effective_resurface = resurface_days or (SAVE_RESURFACE_DAYS if save_decision else None)
    if need_id:
        try:
            if effective_resurface:
                from datetime import timedelta
                resurface_at = (datetime.now(timezone.utc) + timedelta(days=effective_resurface)).isoformat()
                await dc.execute_mutation(
                    "MarkNeedAwaitingResurface", {"id": need_id, "snoozedUntil": resurface_at})
            else:
                await dc.execute_mutation("UpdateNeedStatus", {"id": need_id, "status": "awaiting_customer"})
        except Exception as e:
            logger.warning("send_draft_need_status_failed", need_id=need_id, error=str(e))

    # 3b. close the parked save decision: resolve its sidekick_question Need so it leaves the
    #     Sidekick/Today queue, and record an observation so the agent knows the outreach went out
    #     (a follow-up sweep re-investigates the account later). The run itself stays parked but is
    #     invisible (running-agents only lists status=running) and inert (its task only re-drains on
    #     an explicit resume, which won't happen — and would no-op on the now-sent draft anyway).
    if save_decision:
        try:
            await dc.execute_mutation("ResolveNeed", {"id": save_decision["decision_need_id"]})
            try:
                from services.firestore_service import get_firestore_service
                await get_firestore_service().notify_need_resolved(
                    workspace_id=workspace_id, need_id=save_decision["decision_need_id"])
            except Exception:
                pass
            await record_observation(
                workspace_id, customer_id,
                text="Outreach sent from the conversation — closed the pending approval.",
                agent_run_id=save_decision["run_id"], kind="observed")
            logger.info("send_draft_closed_decision", need_id=need_id,
                        decision_need_id=save_decision["decision_need_id"], run_id=save_decision["run_id"])
        except Exception as e:
            logger.warning("send_draft_close_decision_failed", need_id=need_id, error=str(e))

    # 4. auto-complete the matching save-play step — the CSM shouldn't have to check it off.
    marked_step = None
    try:
        briefs = (await dc.execute_query(
            "GetRiskBriefsWithSteps", {"customerId": customer_id})).get("riskBriefs", [])
        steps = (briefs[0].get("riskPlaySteps_on_brief") if briefs else None) or []
        for s in steps:
            if s.get("done"):
                continue
            if any(k in (s.get("label") or "").lower() for k in _OUTREACH_STEP_KEYWORDS):
                await dc.execute_mutation(
                    "UpdateRiskPlayStep", {"id": s["id"], "done": True, "notes": s.get("notes")})
                marked_step = s["id"]
                break
    except Exception as e:
        logger.warning("send_draft_step_complete_failed", customer_id=customer_id, error=str(e))

    logger.info("draft_sent_simulated", draft_id=draft_id, thread_id=thread_id,
                need_id=need_id, step_marked=marked_step)
    return {"draft_id": draft_id, "thread_id": thread_id, "need_id": need_id, "step_marked": marked_step}

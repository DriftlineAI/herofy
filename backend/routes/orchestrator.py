"""
Orchestrator routes (mounted only when settings.orchestration_enabled).

POST /agents/orchestrator/demo-agent — the scripted demo producer.

Everything downstream of the queue is identical to production; this endpoint just
seeds real records and enqueues tasks. It:
  1. Uses the LOGGED-IN workspace (never creates one); resolves the demo customer
     within it (default match: "bevelpoint").
  2. RESETS prior demo artifacts (all scenarios) so re-runs never duplicate.
  3. Seeds the requested scenario(s) as REAL rows (UI renders real data — zero mocks):
     • risk    — a "went dark" Signal → triage task (worker runs the Risk/Save play)
     • meeting — an upcoming Meeting → meeting_prep task (worker runs the Meeting-brief play)
     • hitl    — a needs_decision task (worker pauses with a sidekick question to answer)
  4. Kicks a drain (risk + meeting run to completion; hitl pauses awaiting the CSM).
"""

import uuid as _uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.logging import get_logger
from db.dataconnect_client import get_dataconnect_client
from middleware.auth import FirebaseUser, get_optional_user
from middleware.scheduler_auth import verify_scheduler_token
from orchestrator.queue import AgentTaskRepository
from orchestrator.queue.consumer import drain_workspace, sweep_due
from orchestrator.huddle_responder import request_sidekick_huddle_reply
from orchestrator.demo import fixture as demo_fixture, reset_workspace, seed_workspace

logger = get_logger("OrchestratorRoute")

router = APIRouter(prefix="/agents/orchestrator", tags=["orchestrator"])

# Per-customer, per-scenario demo event marker — makes reset precise, dupe-proof, AND
# non-colliding across customers/scenarios (running the demo on A then B never wipes A).
def demo_event_id(customer: dict, kind: str = "went_dark") -> str:
    slug = (customer.get("slug") or customer.get("id") or "demo").lower()
    return f"demo:{slug}:{kind}"


async def resume_orchestrator_run(workspace_id: str, need_id: str, answers: dict | None = None) -> None:
    """Durable HITL resume: fold the human's answers into the blocked AgentTask's
    payload, flip it back to pending, and re-drain. Called from the existing /answers
    flow for orchestrator_worker runs. The re-claimed run sees the answers (so the
    worker doesn't re-ask). Safe no-op if no waiting task is found."""
    import json
    dc = get_dataconnect_client()
    task_id = None
    try:
        res = await dc.execute_query("GetWaitingAgentTaskForNeed", {"needId": need_id})
        tasks = res.get("agentTasks", [])
        if not tasks:
            logger.info("orchestrator_resume_no_task", need_id=need_id)
            return
        task = tasks[0]
        task_id = task["id"]
        repo = AgentTaskRepository(workspace_id)
        if answers:
            payload = task.get("payload") or {}
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = {}
            payload["answers"] = answers
            await repo.resume_with_payload(task_id, payload)
        else:
            await repo.resume(task_id)
        await drain_workspace(workspace_id)
    except Exception as e:
        logger.warning("orchestrator_resume_failed", need_id=need_id, error=str(e))
        # Fallback: never leave the task stuck 'waiting'. Flip to pending so any later
        # drain re-claims it (the answers may not be threaded, but it won't hang).
        if task_id:
            try:
                await AgentTaskRepository(workspace_id).resume(task_id)
            except Exception:
                logger.exception("orchestrator_resume_fallback_failed", need_id=need_id)


class DemoAgentRequest(BaseModel):
    workspace_id: str | None = None         # optional; resolved from auth token when omitted
    customer_id: str | None = None          # optional explicit target
    customer_match: str = "bevelpoint"      # else resolve demo customer by name/slug
    scenario: str = "all"                   # all | risk | meeting | hitl


async def _resolve_demo_customer(dc, workspace_id: str, req: DemoAgentRequest) -> dict | None:
    if req.customer_id:
        return await dc.get_customer(req.customer_id)
    customers = await dc.get_customers(workspace_id)
    needle = req.customer_match.lower()
    for c in customers:
        if needle in (c.get("name", "").lower() + " " + c.get("slug", "").lower()):
            return c
    return None


# A "day in the life": varied triggers across clients — the things a CSM actually sees
# (silence, an angry email, an internal Slack note that we dropped the ball, a meeting to
# prep, a decision only a human can make). Each event is assigned to a distinct customer
# (round-robin). `kind` is the per-customer event-id suffix used for idempotent reset.
DAY_EVENTS = [
    {
        # FAN-OUT headline: a broken thing AND churn language → the worker runs BOTH the
        # Support play (draft a reply) AND the Risk/Save play (relationship at risk) on one event.
        "kind": "support_outage", "play": "signal", "need_type": "urgent_support", "risk_overlay": True,
        "signal_kind": "sentiment", "signal_state": "risk", "channel": "email",
        "sender": "VP Ops",
        "subject": "Salesforce integration outage — 3rd time this quarter",
        "sentence": "{name}: integration outage + churn language in an angry email.",
        "evidence": "Email from their VP Ops: \"The Salesforce sync has been down since 9am — records aren't updating and my team is blocked. This is the third outage this quarter; honestly we're starting to evaluate alternatives.\"",
        "summary": "{name}: Salesforce integration is DOWN (team blocked) AND the VP is talking about leaving — angry.",
    },
    {
        # SUPPORT only: a routine technical question, no churn → Support play (drafts a reply), no risk.
        "kind": "support_question", "play": "signal", "need_type": "draft_response_ready",
        "signal_kind": "engagement", "signal_state": "ok", "channel": "email",
        "sender": "IT Admin",
        "subject": "How to configure SAML SSO with Okta?",
        "sentence": "{name} asked how to set up SAML SSO.",
        "evidence": "Email from their IT admin: \"We're rolling out SSO this week — can you point me to how to configure SAML with Okta as our IdP?\"",
        "summary": "{name}: routine how-to question about SAML SSO setup (no risk).",
    },
    {
        # RISK only: gone dark / usage decline → Risk/Save play (save brief + steps), no email thread.
        "kind": "went_dark", "play": "signal", "need_type": "going_dark",
        "signal_kind": "engagement", "signal_state": "risk", "channel": "email",
        "sentence": "{name} has gone dark — no reply to 3 emails in 21 days; logins down 60%.",
        "evidence": "Last inbound 21 days ago (email thread unanswered). Champion (VP Eng) departed. WAU down 60% MoM. Renewal in 60 days.",
        "summary": "{name} went quiet — 3 weeks no reply, usage falling, renewal in 60 days.",
    },
    {"kind": "meeting", "play": "meeting"},
    {"kind": "hitl", "play": "hitl"},
]
ALL_KINDS = [e["kind"] for e in DAY_EVENTS]
_BY_KIND = {e["kind"]: e for e in DAY_EVENTS}


async def _reset_demo(dc, workspace_id: str, customer: dict) -> dict:
    """Delete everything any prior demo run created for this customer across ALL day events.
    Scoped to per-customer event markers — never touches real data."""
    customer_id = customer["id"]
    deleted = {}

    # Risk briefs + steps (FK: steps first).
    briefs = (await dc.execute_query(
        "GetRiskBriefsForCustomer", {"workspaceId": workspace_id, "customerId": customer_id}
    )).get("riskBriefs", [])
    brief_ids = [b["id"] for b in briefs]
    if brief_ids:
        await dc.execute_mutation("DeleteRiskPlayStepsForBriefs", {"briefIds": brief_ids})
        await dc.execute_mutation("DeleteRiskBriefsForCustomer", {"workspaceId": workspace_id, "customerId": customer_id})
    deleted["risk_briefs"] = len(brief_ids)

    # Demo meetings + their briefs (FK: briefs first).
    meetings = (await dc.execute_query(
        "GetDemoMeetings", {"workspaceId": workspace_id, "customerId": customer_id, "externalEventId": demo_event_id(customer, "meeting")}
    )).get("meetings", [])
    meeting_ids = [m["id"] for m in meetings]
    if meeting_ids:
        await dc.execute_mutation("DeleteMeetingBriefsByMeetings", {"meetingIds": meeting_ids})
        await dc.execute_mutation("DeleteMeetingsByIds", {"ids": meeting_ids})
    deleted["meetings"] = len(meeting_ids)

    # Needs + drafts + threads + interactions + signals for every event kind.
    # FK order: DraftResponses → Interactions → Threads → Needs → Signals.
    all_eids = [demo_event_id(customer, kind) for kind in ALL_KINDS]

    # 1. DraftResponses (FK: surfacedInNeedId → Need) — collect all need_ids first.
    all_need_ids = []
    for eid in all_eids:
        prior_needs = (await dc.execute_query(
            "GetNeedsBySourceEvent", {"workspaceId": workspace_id, "sourceEventId": eid}
        )).get("needs", [])
        all_need_ids.extend(n["id"] for n in prior_needs)
    if all_need_ids:
        await dc.execute_mutation("DeleteDraftsByNeeds", {"needIds": all_need_ids})

    # 2. Interactions (FK: threadId → Thread), filtered by sourceEventId.
    await dc.execute_mutation("DeleteDemoInteractionsBySourceEvents", {"sourceEventIds": all_eids})

    # 3. Threads seeded by demo (externalThreadId = eid), FK: needId → Need.
    await dc.execute_mutation("DeleteDemoThreadsByExternalIds", {"externalThreadIds": all_eids})

    # 4. Needs + 5. Signals.
    for eid in all_eids:
        await dc.execute_mutation("DeleteNeedsBySourceEvent", {"workspaceId": workspace_id, "sourceEventId": eid})
        await dc.execute_mutation("DeleteDemoSignals", {"workspaceId": workspace_id, "customerId": customer_id, "inputsHash": eid})
    await dc.execute_mutation("DeleteDemoAgentTasks", {"workspaceId": workspace_id, "customerId": customer_id})
    await dc.execute_mutation("DeleteDemoSidekickItems", {"workspaceId": workspace_id, "customerId": customer_id})
    logger.info("demo_reset", workspace_id=workspace_id, customer_id=customer_id, **deleted)
    return deleted


async def _seed_event(dc, workspace_id, customer, event, repo) -> dict:
    """Seed one day event (risk signal / meeting / hitl) for a customer and enqueue its task."""
    cid, name = customer["id"], customer.get("name", "the customer")
    eid = demo_event_id(customer, event["kind"])
    play = event["play"]

    if play == "signal":
        await dc.execute_mutation("CreateDemoSignal", {
            "workspaceId": workspace_id, "customerId": cid,
            "kind": event["signal_kind"], "state": event["signal_state"],
            "sentence": event["sentence"].format(name=name), "evidenceText": event["evidence"],
            "nextAction": "Assess and act.", "inputsHash": eid,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        })

        # For email-triggered events, seed a real Thread + Interaction so the UI shows a
        # conversation. went_dark has no inbound email (they've gone silent) — skip it.
        thread_id = None
        if event.get("sender") and event["channel"] == "email":
            thread_uuid = str(_uuid.uuid5(_uuid.NAMESPACE_URL, eid))
            subject = event.get("subject") or event["sentence"].format(name=name)
            await dc.execute_mutation("CreateThreadWithId", {
                "id": thread_uuid,
                "workspaceId": workspace_id, "customerId": cid,
                "subject": subject, "channel": "email", "threadType": "customer",
                "status": "open", "externalThreadId": eid,
            })
            interaction_uuid = str(_uuid.uuid5(_uuid.NAMESPACE_URL, eid + ":msg0"))
            await dc.execute_mutation("CreateInteractionFromEvent", {
                "id": interaction_uuid,
                "workspaceId": workspace_id, "customerId": cid, "threadId": thread_uuid,
                "channel": "email", "direction": "customer",
                "senderName": f"{name} — {event['sender']}",
                "subject": subject, "body": event["evidence"],
                "sourceEventId": eid,
            })
            thread_id = thread_uuid

        task_id = await repo.enqueue("triage_signal", customer_id=cid, trigger_type="demo", priority=10, payload={
            "source_event_id": eid, "need_type": event["need_type"],
            "source": {"channel": event["channel"]}, "summary": event["summary"].format(name=name),
            "risk_overlay": event.get("risk_overlay", False),
            "thread_id": thread_id,
        })
        return {"kind": event["kind"], "customer": name, "channel": event["channel"], "need_type": event["need_type"], "task_id": task_id, "thread_id": thread_id}

    if play == "meeting":
        title = f"{name} Quarterly Business Review"
        when = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        m = await dc.execute_mutation("CreateDemoMeeting", {
            "workspaceId": workspace_id, "customerId": cid, "title": title, "scheduledAt": when, "externalEventId": eid,
        })
        meeting_id = (m.get("meeting_insert") or {}).get("id")
        task_id = await repo.enqueue("meeting_prep", customer_id=cid, trigger_type="demo", priority=20, payload={
            "meeting_id": meeting_id, "meeting_title": title, "source_event_id": eid, "summary": f"Prep for {title} (in 5 days).",
        })
        return {"kind": "meeting", "customer": name, "meeting_id": meeting_id, "task_id": task_id}

    if play == "hitl":
        task_id = await repo.enqueue("needs_decision", customer_id=cid, trigger_type="demo", priority=30, payload={
            "source_event_id": eid,
            "question": f"{name} asked for a 20% renewal discount — approve, counter, or hold?",
            "why": "Pricing authority is yours; the agent will proceed once you decide.",
            "summary": f"{name} needs a pricing decision before renewal outreach.",
        })
        return {"kind": "hitl", "customer": name, "task_id": task_id}
    return {}


class HuddleMentionRequest(BaseModel):
    huddle_id: str


@router.post("/huddle-mention")
async def huddle_mention(request: HuddleMentionRequest, background_tasks: BackgroundTasks) -> dict:
    """Producer for @sidekick huddle replies. Track A calls this after posting a huddle
    message whose mentions include "sidekick": it enqueues a huddle_reply task and kicks a
    drain, so the worker posts an agent HuddleMessage back into the discussion."""
    task_id = await request_sidekick_huddle_reply(request.huddle_id)
    if not task_id:
        return {"status": "skipped", "reason": "huddle not found"}
    # Drain that huddle's workspace so the reply posts promptly.
    dc = get_dataconnect_client()
    h = (await dc.execute_query("GetHuddlePublic", {"id": request.huddle_id})).get("huddle") or {}
    ws = (h.get("workspace") or {}).get("id")
    if ws:
        background_tasks.add_task(drain_workspace, ws)
    return {"status": "enqueued", "task_id": task_id, "huddle_id": request.huddle_id}


@router.post("/sweep")
async def sweep(
    workspace_id: str | None = Query(default=None, description="Drain a single workspace; omit to sweep all with due tasks"),
    _verified: bool = Depends(verify_scheduler_token),
) -> dict:
    """Periodic 'production wake': claim + process all DUE (scheduledFor <= now) pending
    tasks, so self-scheduled follow-ups and scheduled sweeps fire on time.

    Auth: Cloud Scheduler OIDC in prod (verify_scheduler_token); bypassed in development,
    so it's curl-able manually. Idempotent — safe to call on any cadence.
    """
    if workspace_id:
        processed = await drain_workspace(workspace_id)
        return {"status": "ok", "workspace_id": workspace_id, "processed": processed}
    result = await sweep_due()
    return {"status": "ok", **result}


class RiskPlayRequest(BaseModel):
    workspace_id: str | None = None      # optional; resolved from auth token when omitted
    customer_id: str
    description: str                      # the CSM's short "what happened" (becomes the evidence)
    need_type: str = "renewal_at_risk"   # risk framing hint for the surfaced Need


# Risk-appropriate Need types the manual trigger may stamp (mirrors the play's own allow-list).
_RISK_NEED_TYPES = {
    "going_dark", "renewal_at_risk", "frustrated_signal",
    "open_commitment_overdue", "approaching_renewal",
    "champion_departed", "onboarding_behind",
}


@router.post("/risk-play")
async def trigger_risk_play(
    request: RiskPlayRequest,
    background_tasks: BackgroundTasks,
    user: FirebaseUser | None = Depends(get_optional_user),
):
    """Manually spin up the Risk/Save play for a customer from a short free-text
    description of what happened (e.g. "on our QBR they said they're evaluating
    competitors and may not renew").

    This is the human-initiated counterpart to a detected signal: it seeds a risk
    Signal carrying the description as evidence, enqueues a triage task, and kicks a
    drain. The worker — via its deterministic risk backstop — runs the Risk/Save play,
    producing a RiskBrief + save-play steps + a renewal_at_risk Need. The description
    becomes the evidence the strategist (and researcher) reason over, so the AI adapts
    the workspace's risk playbook to what the CSM just learned on the call.
    """
    if not user:
        return JSONResponse(status_code=401, content={"error": {"code": "UNAUTHENTICATED", "message": "Firebase auth token required."}})

    description = (request.description or "").strip()
    if not description:
        return JSONResponse(status_code=400, content={"error": {"code": "MISSING_DESCRIPTION", "message": "Tell the agent briefly what happened."}})

    dc = get_dataconnect_client()

    # Resolve workspace: explicit body param → first workspace the authed user belongs to.
    workspace_id = request.workspace_id
    user_data = (await dc.execute_query("GetUserById", {"userId": user.uid})).get("users", [])
    memberships = (user_data[0].get("workspaceMembers_on_user") or []) if user_data else []
    member_workspace_ids = {m["workspace"]["id"] for m in memberships}
    if not workspace_id:
        if not memberships:
            return JSONResponse(status_code=400, content={"error": {"code": "NO_WORKSPACE", "message": "Authenticated user belongs to no workspace."}})
        workspace_id = memberships[0]["workspace"]["id"]
    elif workspace_id not in member_workspace_ids:
        return JSONResponse(status_code=403, content={"error": {"code": "FORBIDDEN", "message": "You do not have access to this workspace."}})

    # Verify the customer belongs to this workspace (also gets us the display name).
    customers = await dc.get_customers(workspace_id)
    customer = next((c for c in customers if c.get("id") == request.customer_id), None)
    if not customer:
        return JSONResponse(status_code=404, content={"error": {"code": "CUSTOMER_NOT_FOUND", "message": "No such customer in this workspace."}})
    name = customer.get("name", "the customer")

    # Unique event id per trigger → never deduped against a prior brief; each manual
    # flag is its own event.
    eid = f"manual:risk:{request.customer_id}:{_uuid.uuid4().hex[:8]}"
    need_type = request.need_type if request.need_type in _RISK_NEED_TYPES else "renewal_at_risk"

    await dc.execute_mutation("CreateDemoSignal", {
        "workspaceId": workspace_id, "customerId": request.customer_id,
        "kind": "sentiment", "state": "risk",
        "sentence": f"{name}: CSM flagged churn risk — {description[:120]}",
        "evidenceText": description,
        "nextAction": "Assess and act.", "inputsHash": eid,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    })

    repo = AgentTaskRepository(workspace_id)
    task_id = await repo.enqueue("triage_signal", customer_id=request.customer_id, trigger_type="manual", priority=5, payload={
        "source_event_id": eid, "need_type": need_type,
        "source": {"channel": "manual"}, "summary": f"{name}: {description}",
    })
    background_tasks.add_task(drain_workspace, workspace_id)

    logger.info("manual_risk_play_enqueued", workspace_id=workspace_id, customer_id=request.customer_id, task_id=task_id)
    return {"status": "enqueued", "customer": name, "task_id": task_id, "need_type": need_type, "source_event_id": eid}


@router.post("/demo-agent")
async def demo_agent(
    request: DemoAgentRequest,
    background_tasks: BackgroundTasks,
    user: FirebaseUser | None = Depends(get_optional_user),
):
    """Seed a 'day in the life' and kick a drain.

    scenario=all (default): a realistic day across SEVERAL clients — a customer gone dark,
    an angry email, an internal Slack note that we dropped the ball, a meeting to prep, and
    a pricing decision for the human. Each is a real event added to the queue; the worker
    triages each and the Today queue fills with a varied spread of Needs.

    scenario=risk|meeting|hitl: a single event on the matched customer (targeted testing).
    """
    if not user:
        return JSONResponse(status_code=401, content={"error": {"code": "UNAUTHENTICATED", "message": "Firebase auth token required."}})

    dc = get_dataconnect_client()

    # Resolve workspace: explicit body param → first workspace the authed user belongs to.
    workspace_id = request.workspace_id
    user_data = (await dc.execute_query("GetUserById", {"userId": user.uid})).get("users", [])
    memberships = (user_data[0].get("workspaceMembers_on_user") or []) if user_data else []
    member_workspace_ids = {m["workspace"]["id"] for m in memberships}

    if not workspace_id:
        if not memberships:
            return JSONResponse(status_code=400, content={"error": {"code": "NO_WORKSPACE", "message": "Authenticated user belongs to no workspace."}})
        workspace_id = memberships[0]["workspace"]["id"]
    elif workspace_id not in member_workspace_ids:
        return JSONResponse(status_code=403, content={"error": {"code": "FORBIDDEN", "message": "You do not have access to this workspace."}})
    scenario = (request.scenario or "all").lower()
    if scenario not in {"all", "day", "support", "risk", "meeting", "hitl"}:
        scenario = "all"

    repo = AgentTaskRepository(workspace_id)

    # --- Targeted single-event scenario (one customer) ---
    if scenario in {"support", "risk", "meeting", "hitl"}:
        customer = await _resolve_demo_customer(dc, workspace_id, request)
        if not customer:
            return JSONResponse(status_code=404, content={"error": {
                "code": "DEMO_CUSTOMER_NOT_FOUND",
                "message": (
                    f"No demo customer matching '{request.customer_match}' in this workspace. "
                    "Seed one, or pass customer_id / customer_match explicitly."
                ),
            }})
        await _reset_demo(dc, workspace_id, customer)
        kind = {"support": "support_outage", "risk": "went_dark", "meeting": "meeting", "hitl": "hitl"}[scenario]
        seeded = [await _seed_event(dc, workspace_id, customer, _BY_KIND[kind], repo)]
        background_tasks.add_task(drain_workspace, workspace_id)
        return {"status": "enqueued", "scenario": scenario, "customer": customer.get("name"), "seeded": seeded}

    # --- Full day-in-the-life across several customers ---
    customers = await dc.get_customers(workspace_id)
    if not customers:
        return JSONResponse(status_code=404, content={"error": {
            "code": "NO_CUSTOMERS", "message": "No customers in this workspace to run the demo against.",
        }})
    # Assign one event per customer (round-robin if fewer customers than events).
    chosen = [customers[i % len(customers)] for i in range(len(DAY_EVENTS))]
    reset_done: set[str] = set()
    seeded = []
    for event, customer in zip(DAY_EVENTS, chosen):
        if customer["id"] not in reset_done:
            await _reset_demo(dc, workspace_id, customer)
            reset_done.add(customer["id"])
        seeded.append(await _seed_event(dc, workspace_id, customer, event, repo))

    # Kick a drain: risk + meeting tasks run to completion; the hitl task pauses (waiting).
    background_tasks.add_task(drain_workspace, workspace_id)

    logger.info("demo_day_seeded", workspace_id=workspace_id, events=len(seeded), customers=len(reset_done))
    return {
        "status": "enqueued",
        "scenario": "day",
        "workspace_id": workspace_id,
        "events": len(seeded),
        "customers": len(reset_done),
        "seeded": seeded,
    }


class SeedWorkspaceRequest(BaseModel):
    workspace_id: str | None = None     # optional; resolved from auth token when omitted
    profile: str = "full"               # full | lane1 | lane2
    reset: bool = True                  # wipe the workspace before seeding (idempotent re-runs)


@router.post("/seed-workspace")
async def seed_workspace_route(
    request: SeedWorkspaceRequest,
    user: FirebaseUser | None = Depends(get_optional_user),
):
    """Seed the full Northcrest demo fixture into a workspace (reset-then-seed).

    Lays down real rows the UI renders — 13 customers with stakeholders, goals,
    milestones, 90-day threads/interactions (backdated, so POST /sweep fires the
    going-dark detector organically on Quietfield), pre-baked sales→CS handoff briefs +
    plans for the fresh-handoff customers, and the current open Needs that populate Today
    and Conversations on arrival. NO tasks are enqueued — the live 'watch the agent work'
    moments stay with /demo-agent (escalations) and /sweep (going dark).

    ⚠️ reset=True deletes ALL customers/threads/needs/etc. in the target workspace.
    Intended for throwaway demo workspaces, not real ones.
    """
    if not user:
        return JSONResponse(status_code=401, content={"error": {"code": "UNAUTHENTICATED", "message": "Firebase auth token required."}})

    dc = get_dataconnect_client()

    # Resolve workspace: explicit body param → first workspace the authed user belongs to.
    workspace_id = request.workspace_id
    user_data = (await dc.execute_query("GetUserById", {"userId": user.uid})).get("users", [])
    memberships = (user_data[0].get("workspaceMembers_on_user") or []) if user_data else []
    member_workspace_ids = {m["workspace"]["id"] for m in memberships}
    if not workspace_id:
        if not memberships:
            return JSONResponse(status_code=400, content={"error": {"code": "NO_WORKSPACE", "message": "Authenticated user belongs to no workspace."}})
        workspace_id = memberships[0]["workspace"]["id"]
    elif workspace_id not in member_workspace_ids:
        return JSONResponse(status_code=403, content={"error": {"code": "FORBIDDEN", "message": "You do not have access to this workspace."}})

    profile = (request.profile or "full").lower()
    if profile not in {"full", "lane1", "lane2"}:
        profile = "full"

    # Impersonate the authed member so the seed ops' @check(auth.uid) gates pass on the admin
    # surface (the un-impersonated admin request can't read auth.uid).
    with dc.impersonate(user.uid):
        reset_summary = await reset_workspace(workspace_id) if request.reset else None
        result = await seed_workspace(workspace_id, profile=profile)

    logger.info("demo_workspace_seeded", workspace_id=workspace_id, profile=profile,
                counts=result.counts, errors=len(result.errors))
    return {
        "status": "seeded",
        "workspace_id": workspace_id,
        "profile": profile,
        "reset": reset_summary,
        "counts": result.counts,
        "errors": result.errors,
    }


@router.get("/seed-workspace/inspect")
async def inspect_workspace_seed(
    workspace_id: str | None = Query(default=None),
    user: FirebaseUser | None = Depends(get_optional_user),
):
    """Read-only: how many customers a workspace has, and how many are demo accounts.

    'demo_customers' matches seeded customers by their fixture slug — a lightweight
    stand-in for a real demo/client account flag (a tracked future item). Lets the Lab
    show whether the chosen workspace already holds the demo set before you wipe it.
    """
    if not user:
        return JSONResponse(status_code=401, content={"error": {"code": "UNAUTHENTICATED", "message": "Firebase auth token required."}})

    dc = get_dataconnect_client()
    user_data = (await dc.execute_query("GetUserById", {"userId": user.uid})).get("users", [])
    memberships = (user_data[0].get("workspaceMembers_on_user") or []) if user_data else []
    member_workspace_ids = {m["workspace"]["id"] for m in memberships}
    if not workspace_id:
        if not memberships:
            return JSONResponse(status_code=400, content={"error": {"code": "NO_WORKSPACE", "message": "Authenticated user belongs to no workspace."}})
        workspace_id = memberships[0]["workspace"]["id"]
    elif workspace_id not in member_workspace_ids:
        return JSONResponse(status_code=403, content={"error": {"code": "FORBIDDEN", "message": "You do not have access to this workspace."}})

    with dc.impersonate(user.uid):
        customers = await dc.get_customers(workspace_id)
    demo_slugs = {c.slug for c in demo_fixture.CUSTOMERS}
    demo_present = sum(1 for c in customers if c.get("slug") in demo_slugs)
    return {
        "workspace_id": workspace_id,
        "customers_total": len(customers),
        "demo_customers": demo_present,
        "demo_expected": len(demo_slugs),
    }

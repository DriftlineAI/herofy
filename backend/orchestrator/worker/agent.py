"""
The autonomous worker — net-new ADK `LlmAgent` + `PlanReActPlanner`.

Per claimed task it: investigates the account, DECIDES a response (open-ended —
not pre-scripted), dispatches the Risk/Save play as an `AgentTool`, records an
account observation, and self-schedules a follow-up by enqueuing a future task.

Reliability: the play's persistence stages are deterministic, and `run_worker`
adds a backstop — if the worker finishes without the play having run on a clearly
risky account, it runs the play once so the demo always produces real artifacts.
"""

import json
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.planners import PlanReActPlanner
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from core.logging import get_logger
from core.model_config import get_model, ModelUseCase

from agents.handoff_auto.tools.context import get_customer_info as _get_customer_info

from .. import artifacts
from ..memory.context import make_context_load_callback
from ..memory.recall import memory_recall as _memory_recall
from ..plays.risk_save import build_risk_save_play, STATE_BRIEF_ID, STATE_NEED_ID
from ..plays.meeting_brief import build_meeting_brief_play
from ..plays.support import build_support_play
from ..queue.repository import AgentTaskRepository
from ..runtime.callbacks import before_agent_callback, after_agent_callback, stream_status, langfuse_model_cb, stream_tool_output
from ..runtime.runner import APP_NAME, build_runner, default_run_config
from ..runtime.state import initial_state, KEY_RUN_ID
from . import WorkerOutcome

logger = get_logger("OrchestratorWorker")

STATE_PAUSE_NEED = "pause_need_id"
STATE_PAUSE_QUESTIONS = "pause_questions"
STATE_FOLLOW_UP = "follow_up_task_id"
STATE_OBSERVED = "observation_recorded"


async def _surface_sidekick_question(
    workspace_id, customer_id, customer_name, run_id, question, why, source_event_id,
    *, structured_type=None, options=None, question_context=None,
) -> tuple[str, list[dict]]:
    """Create a sidekick_question Need and the matching clarifying-question payload.
    Shared by the ask_human tool and the deterministic needs_decision pause. The
    returned questions are stored on the AgentRun (clarifyingQuestions) by the consumer
    so the existing NeedDetail answer form renders them.

    `why` is the short need lede/reasoning; `question_context` (when given) is the richer
    text shown on the decision screen itself — e.g. the brief summary + drafted email —
    so the CSM can see what they're approving without bloating the Need card."""
    import uuid as _uuid
    from db.dataconnect_client import get_dataconnect_client
    from core.types import ClarifyingQuestion, StructuredQuestionType
    dc = get_dataconnect_client()
    need_id = str(_uuid.uuid4())
    await dc.execute_mutation("CreateNeedWithId", {
        "id": need_id, "workspaceId": workspace_id, "customerId": customer_id,
        "type": "sidekick_question", "headline": f"{customer_name}: {question}",
        "lede": why, "priorityRank": 4, "agentReasoning": why,
        "handbookVersionId": None, "agentRunId": run_id, "sourceEventId": source_event_id,
    })
    try:
        from services.firestore_service import get_firestore_service
        await get_firestore_service().notify_need_created(
            workspace_id=workspace_id, need_id=need_id, need_type="sidekick_question",
            customer_name=customer_name,
        )
    except Exception as e:  # non-fatal
        pass
    q = ClarifyingQuestion(
        field="response", question=question, context=question_context or why,
        structured_type=structured_type or StructuredQuestionType.FREEFORM,
        options=options, required=True,
    )
    return need_id, [q.model_dump()]

WORKER_INSTRUCTION = """You are Herofy's autonomous Customer Success worker. A task has arrived:

  Task type:     {task_type}
  Classified as: {need_type}
  Customer:      {customer_name}
  Summary:       {task_summary}

ANSWERS the CSM already gave you (if any — do NOT re-ask these; act on them):
{prior_answers}

Work the task:

1. INVESTIGATE — call investigate_account() first. Always. Do not form a plan until you have
   read the current signals, milestone status, and interaction history.

2. DECIDE — let the data drive the decision. The task type and summary are hints, not verdicts.
   One situation can need more than one response, or none at all.

3. ACT — run the play that fits what the data shows:
   • Technical issue, support question, or customer complaint → `support_play`
   • Upcoming customer meeting → `meeting_brief_play`
   • Account gone dark, churn/renewal risk, stalled onboarding, stakeholder friction → `risk_save_play`
   • Real churn risk alongside another issue → run `risk_save_play` as an overlay too.
   • Nothing actionable (positive signal, simple thank-you) → run no play.

   RUN BOTH plays when an active technical crisis is ALSO driving churn risk — an ongoing
   outage, broken integration, or unresolved issue paired with anger, escalation, or
   "evaluating alternatives" language. In that case run `support_play` (to triage and draft
   the reply the customer needs now) AND `risk_save_play` (to surface the save strategy for
   the relationship). One addresses the immediate problem; the other addresses the account.
   Don't make the customer wait on a reply just because you opened a save play.

4. OBSERVE — call record_observation() with a one-line note on what you found and did.

5. FOLLOW UP — if you ran `risk_save_play`, call schedule_follow_up(days=3, ...).

On a follow_up task: re-investigate fresh every time. If the customer has re-engaged and
conditions have genuinely improved, record that and stop. If they are STILL dark, milestones
are still blocked, or the risk signals persist — the situation is unresolved. Run the
appropriate play as if you just discovered it. A previous play running does not mean the
problem is solved.

Be decisive and evidence-based. Act on what the data shows, not on what the task label implies.
"""


def build_worker_agent(workspace_id: str, customer_id: str, customer_name: str, notion_token: str | None = None) -> LlmAgent:
    """Build the worker bound to one task's account, with the play as a tool."""

    async def investigate_account(tool_context: ToolContext) -> str:
        """Get the full current picture of the customer plus relevant history."""
        await stream_status(
            tool_context.state.get(KEY_RUN_ID), "running", "investigate_account",
            f"Investigating {customer_name}…", progress_pct=15,
            customer_id=customer_id, customer_name=customer_name,
        )
        info = await _get_customer_info(customer_id, workspace_id)
        recall = await _memory_recall(
            "why might this account be at risk", "customer",
            workspace_id=workspace_id, customer_id=customer_id,
        )
        return json.dumps({"customer": info, "history": json.loads(recall)}, default=str)

    async def record_observation(note: str, tool_context: ToolContext) -> str:
        """Record a one-line account observation/tip in the CSM activity feed."""
        await artifacts.record_observation(
            workspace_id, customer_id, text=note,
            agent_run_id=tool_context.state.get(KEY_RUN_ID), kind="observed",
        )
        tool_context.state[STATE_OBSERVED] = True
        return "observation recorded"

    async def ask_human(question: str, why: str, tool_context: ToolContext) -> str:
        """Pause and ask the CSM a question. Use ONLY when you genuinely cannot
        proceed without a specific human decision the data can't answer. For a clear
        churn/renewal-risk account, do NOT ask — act and run the save play instead."""
        run_id = tool_context.state.get(KEY_RUN_ID)
        await stream_status(
            run_id, "running", "ask_human", "Asking the CSM a question…",
            progress_pct=50, customer_id=customer_id, customer_name=customer_name,
        )
        payload = tool_context.state.get("payload") or {}
        need_id, questions = await _surface_sidekick_question(
            workspace_id, customer_id, customer_name, run_id, question, why,
            payload.get("source_event_id"),
        )
        tool_context.state[STATE_PAUSE_NEED] = need_id
        tool_context.state[STATE_PAUSE_QUESTIONS] = questions
        return "paused — waiting for the CSM to answer."

    async def schedule_follow_up(days: int, reason: str, tool_context: ToolContext) -> str:
        """Self-schedule a follow-up task on this account `days` from now."""
        payload = tool_context.state.get("payload") or {}
        task_id = await _enqueue_follow_up(
            workspace_id, customer_id, customer_name, days, reason,
            source_event_id=payload.get("source_event_id"),
        )
        tool_context.state[STATE_FOLLOW_UP] = task_id
        return f"follow-up scheduled (task {task_id})"

    risk_play = build_risk_save_play(workspace_id, customer_id, notion_token=notion_token, after_agent_callback=after_agent_callback)
    meeting_play = build_meeting_brief_play(workspace_id, customer_id, notion_token=notion_token, after_agent_callback=after_agent_callback)
    support_play = build_support_play(workspace_id, customer_id, notion_token=notion_token, after_agent_callback=after_agent_callback)

    # compose context-load + progress-stream as the worker's before-agent hook
    _load_context = make_context_load_callback()

    async def _before(callback_context):
        await _load_context(callback_context)
        await before_agent_callback(callback_context)
        return None

    return LlmAgent(
        name="orchestrator_worker",
        model=get_model(ModelUseCase.SIGNAL_ANALYSIS),
        planner=PlanReActPlanner(),
        instruction=WORKER_INSTRUCTION,
        tools=[
            investigate_account,
            AgentTool(agent=support_play),
            AgentTool(agent=risk_play),
            AgentTool(agent=meeting_play),
            record_observation,
            schedule_follow_up,
            ask_human,
        ],
        before_agent_callback=_before,
        after_agent_callback=after_agent_callback,
        after_model_callback=langfuse_model_cb,
        after_tool_callback=stream_tool_output,
    )


# Classified need_type -> PRIMARY play (the worker may also fan out a risk co-play on top).
_SUPPORT_TYPES = {"urgent_support", "draft_response_ready"}
_MEETING_TYPES = {"meeting_prep_ready"}


def _primary_play_kind(task_type: str, need_type: str | None) -> str:
    """The PRIMARY play a task's classified type maps to. Risk is the default 'save' motion."""
    if task_type == "meeting_prep" or need_type in _MEETING_TYPES:
        return "meeting"
    if task_type == "support_issue" or need_type in _SUPPORT_TYPES:
        return "support"
    return "risk"


async def run_worker(task: dict[str, Any], *, run_id: str, workspace_id: str) -> WorkerOutcome:
    """Run the autonomous worker for one claimed task. Returns the outcome the
    consumer uses to complete / pause / fail the task."""
    customer = task.get("customer") or {}
    customer_id = customer.get("id")
    customer_name = customer.get("name") or "this customer"
    payload = task.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {}

    # @sidekick huddle reply — a focused, deterministic handler (no play dispatch).
    # Posts an agent HuddleMessage back into the internal discussion.
    if task.get("taskType") == "huddle_reply":
        from ..huddle_responder import handle_huddle_reply
        result = await handle_huddle_reply(task, run_id=run_id, workspace_id=workspace_id)
        return WorkerOutcome(status="done", result=result)

    if not customer_id:
        # Workspace-level tasks aren't part of the demo path; ack as done.
        return WorkerOutcome(status="done", result={"note": "no customer in scope"})

    # Deterministic HITL pause for `needs_decision` tasks that haven't been answered yet —
    # guarantees a clean, demoable pause (no reliance on the LLM choosing to ask). Once the
    # CSM answers (answers folded into payload), we fall through and run the agent for real.
    if task.get("taskType") == "needs_decision" and not (payload.get("answers")):
        question = payload.get("question") or "How would you like the agent to proceed?"
        why = payload.get("why") or "The agent needs a decision from you before continuing."
        need_id, questions = await _surface_sidekick_question(
            workspace_id, customer_id, customer_name, run_id, question, why, payload.get("source_event_id"),
        )
        return WorkerOutcome(status="waiting", blocking_need_id=need_id, clarifying_questions=questions)

    # Fetch the workspace's Notion *MCP* OAuth token so the researcher can call mcp.notion.com.
    # This is the `notion_mcp` integration (separate OAuth + PKCE flow), NOT the REST `notion`
    # token — the REST token is rejected by the hosted MCP server with 401. get_valid_token
    # auto-refreshes the short-lived (~1h) MCP token server-side. Best-effort: if notion_mcp
    # isn't connected or refresh fails, notion_token stays None and the researcher runs without
    # Notion (graceful degradation via _SafeMcpToolset).
    notion_token: str | None = None
    try:
        from services.integration_service_dc import IntegrationServiceDC
        from db.dataconnect_client import get_dataconnect_client
        notion_token = await IntegrationServiceDC(get_dataconnect_client(), workspace_id).get_valid_token("notion_mcp")
    except Exception:
        pass

    agent = build_worker_agent(workspace_id, customer_id, customer_name, notion_token=notion_token)

    from ..runtime.services import get_session_service
    session_service = get_session_service()
    state = initial_state(
        run_id=run_id, task_id=task["id"], workspace_id=workspace_id,
        customer_id=customer_id, customer_name=customer_name,
        trigger_type=task.get("triggerType", "demo"), payload=payload,
    )
    # Keys the worker instruction templates ({task_type}, {task_summary};
    # {customer_name} is already KEY_CUSTOMER_NAME). Must be in the state dict
    # passed to create_session so the stored session has them.
    state["task_type"] = task.get("taskType", "task")
    state["task_summary"] = payload.get("summary", "assess and act")
    state["need_type"] = payload.get("need_type") or "(unclassified)"  # classifier stamp for routing
    state["meeting_title"] = payload.get("meeting_title", "the upcoming meeting")  # for the meeting writer
    # HITL resume: prior answers folded into the payload by resume_orchestrator_run.
    answers = payload.get("answers")
    state["prior_answers"] = (
        "\n".join(f"- {k}: {v}" for k, v in answers.items()) if isinstance(answers, dict) and answers
        else "(none)"
    )

    # DEMO: act on the save-play decision deterministically instead of re-running the LLM — the
    # keystone actually pays off. approve → simulate the send (the single send action shared with
    # the UI Send button); counter/hold → leave the draft for the CSM. Gated on demo_enabled so
    # prod keeps the agent-resume behavior.
    from config import get_settings as _get_settings
    if _get_settings().demo_enabled and isinstance(answers, dict) and answers:
        decision = str(next(iter(answers.values()), "")).strip().lower()
        if decision in ("approve", "counter", "hold"):
            if decision == "approve":
                # Resolve the thread by the customer's pending draft (robust — no deterministic-id
                # guessing, which mismatched on workspace/customer id formatting).
                sent = await artifacts.send_draft_response(
                    customer_id=customer_id, workspace_id=workspace_id,
                    resurface_days=artifacts.SAVE_RESURFACE_DAYS)
                await artifacts.record_observation(
                    workspace_id, customer_id,
                    text=f"Sent the re-engagement email to {customer_name} on your approval.",
                    agent_run_id=run_id, kind="observed")
                await stream_status(run_id, "running", "sent", "Outreach sent — awaiting their reply.",
                                    progress_pct=100, customer_id=customer_id, customer_name=customer_name)
                logger.info("demo_hitl_approved_sent", run_id=run_id, sent=bool(sent))
            else:
                note = ("Holding — you'll adjust the draft before it goes out." if decision == "counter"
                        else "Holding the outreach for now.")
                await artifacts.record_observation(
                    workspace_id, customer_id, text=f"{customer_name}: {note}",
                    agent_run_id=run_id, kind="observed")
                await stream_status(run_id, "running", "held", note, progress_pct=100,
                                    customer_id=customer_id, customer_name=customer_name)
                logger.info("demo_hitl_decision", run_id=run_id, decision=decision)
            return WorkerOutcome(status="done", result={"decision": decision})

    session = await session_service.create_session(app_name=APP_NAME, user_id=workspace_id, state=state)

    runner = build_runner(agent)
    message = types.Content(role="user", parts=[types.Part(text=(
        f"Work this {task.get('taskType','task')} for {customer_name}: "
        f"{payload.get('summary','assess and act')}"
    ))])

    try:
        async for _event in runner.run_async(
            user_id=workspace_id, session_id=session.id,
            new_message=message, run_config=default_run_config(),
        ):
            pass
    except Exception as e:
        logger.exception("worker_run_error", run_id=run_id, error=str(e))
        return WorkerOutcome(status="failed", error=str(e))

    # Re-hydrate final session state.
    final = await session_service.get_session(app_name=APP_NAME, user_id=workspace_id, session_id=session.id)
    fstate = final.state if final else session.state

    # HITL pause?
    if fstate.get(STATE_PAUSE_NEED):
        return WorkerOutcome(
            status="waiting",
            blocking_need_id=fstate[STATE_PAUSE_NEED],
            clarifying_questions=fstate.get(STATE_PAUSE_QUESTIONS),
        )

    # Backstop the PRIMARY play (guarantee its artifact); the risk co-play is the worker's
    # judgment, so it gets no backstop. Gate on the DB (source of truth), not session state.
    from db.dataconnect_client import get_dataconnect_client
    dc = get_dataconnect_client()
    task_type = task.get("taskType", "triage_signal")
    need_type = payload.get("need_type")
    primary = _primary_play_kind(task_type, need_type)
    event_id = payload.get("source_event_id") or f"auto:{customer_id}"
    meeting_id = payload.get("meeting_id")
    backstopped = False

    async def _risk_brief():
        return (await dc.execute_query("GetRiskBriefByEvent", {"workspaceId": workspace_id, "inputsHash": event_id})).get("riskBriefs", [])

    async def _meeting_brief():
        if not meeting_id:
            return []
        return (await dc.execute_query("GetMeetingBriefByMeeting", {"meetingId": meeting_id})).get("meetingBriefs", [])

    async def _support_need():
        # The Support play surfaces a support-typed Need for this event; gate on that.
        if not dc.has_operation("GetNeedsBySourceEvent"):
            return []
        needs = (await dc.execute_query(
            "GetNeedsBySourceEvent", {"workspaceId": workspace_id, "sourceEventId": event_id}
        )).get("needs", [])
        return [n for n in needs if n.get("type") in _SUPPORT_TYPES]

    if primary == "support":
        existing = await _support_need()
        if not existing:
            await stream_status(run_id, "running", "support_play",
                                "Drafting a support reply (backstop)…", progress_pct=70,
                                customer_id=customer_id, customer_name=customer_name)
            await _run_play_standalone(
                build_support_play(workspace_id, customer_id, after_agent_callback=after_agent_callback),
                workspace_id, customer_id, customer_name, run_id, payload,
            )
            backstopped = True
            existing = await _support_need()
        primary_id = existing[0]["id"] if existing else None
        obs_text = f"Drafted a support reply for {customer_name}."
        event_summary = payload.get("summary") or "Handled a support issue."
    elif primary == "meeting":
        existing = await _meeting_brief()
        if not existing and meeting_id:
            await stream_status(run_id, "running", "meeting_brief_play",
                                "Preparing meeting brief (backstop)…", progress_pct=70,
                                customer_id=customer_id, customer_name=customer_name)
            await _run_play_standalone(
                build_meeting_brief_play(workspace_id, customer_id, after_agent_callback=after_agent_callback),
                workspace_id, customer_id, customer_name, run_id, payload,
            )
            backstopped = True
            existing = await _meeting_brief()
        primary_id = existing[0]["id"] if existing else None
        obs_text = f"Prepared a meeting brief for {customer_name}."
        event_summary = f"Prepared a meeting brief for {payload.get('meeting_title','an upcoming meeting')}."
    else:  # risk (default)
        existing = await _risk_brief()
        if not existing:
            await stream_status(run_id, "running", "risk_save_play",
                                "Running save play (backstop)…", progress_pct=70,
                                customer_id=customer_id, customer_name=customer_name)
            await _run_play_standalone(
                build_risk_save_play(workspace_id, customer_id, after_agent_callback=after_agent_callback),
                workspace_id, customer_id, customer_name, run_id, payload,
            )
            backstopped = True
            existing = await _risk_brief()
        primary_id = existing[0]["id"] if existing else None
        obs_text = f"Reviewed {customer_name}: surfaced a save play for CSM review."
        event_summary = (existing[0].get("whatChanged") if existing else None) or payload.get("summary") or "Reviewed account."

    # Deterministic risk OVERLAY: when the classifier flags churn risk on a NON-risk primary
    # (an "it's broken AND we're leaving" email → support + risk), guarantee the Risk/Save play
    # also runs — a distinct renewal_at_risk Need beside the primary. Risk is an ORTHOGONAL
    # overlay (not every support issue earns one); the explicit `risk_overlay` stamp just makes
    # it reliable. The worker LLM may also add it itself on non-stamped real signals.
    if primary != "risk" and payload.get("risk_overlay") and not await _risk_brief():
        await stream_status(run_id, "running", "risk_save_play",
                            "Adding a save play (risk overlay)…", progress_pct=80,
                            customer_id=customer_id, customer_name=customer_name)
        await _run_play_standalone(
            build_risk_save_play(workspace_id, customer_id, after_agent_callback=after_agent_callback),
            workspace_id, customer_id, customer_name, run_id,
            {**payload, "need_type": "renewal_at_risk"},
        )

    # DEMO keystone: once the save play has produced a brief AND drafted the re-engagement email,
    # pause for the human's decision (approve / counter / hold) — showing the REAL brief + email so
    # the CSM sees exactly what they're approving (not a canned prompt). Gated on demo_enabled so
    # prod runs to completion; skipped on resume (answers present). Reuses the existing
    # waiting_for_input + /answers + resume path — the consumer turns this WorkerOutcome into a pause.
    from config import get_settings as _get_settings
    if _get_settings().demo_enabled and primary == "risk" and existing and not payload.get("answers"):
        from core.types import StructuredQuestionType
        # Read the persisted draft back from the DB (the play ran in its own runner/backstop, so its
        # state doesn't reach here). The outreach thread id is deterministic — recompute it.
        import uuid as _uuid
        brief = existing[0] if existing else {}
        what_changed = (brief.get("whatChanged") or "").strip()
        evidence = (brief.get("evidenceText") or "").strip()
        thread_id = str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"risk-outreach:{workspace_id}:{customer_id}"))
        draft = {}
        try:
            rows = (await dc.execute_query("GetDraftResponse", {"threadId": thread_id})).get("draftResponses", [])
            draft = rows[0] if rows else {}
        except Exception as e:  # non-fatal — fall back to a plan-only decision
            logger.warning("demo_hitl_draft_read_failed", run_id=run_id, error=str(e))

        # Build the decision context the CSM sees: the report (brief) + the drafted email.
        # Sections use "## " headers (a stable, frontend-parseable contract — see the decision
        # screen's section renderer) so the dense block reads as structured cards, not a wall.
        ctx_parts = []
        if what_changed:
            ctx_parts.append(f"## What changed\n{what_changed}")
        if evidence:
            ctx_parts.append(f"## Evidence\n{evidence}")
        if draft.get("body"):
            subj = draft.get("subject") or "(no subject)"
            ctx_parts.append(f"## Drafted email\nSubject: {subj}\n\n{draft['body']}")
        question_context = "\n\n".join(ctx_parts) or (
            f"{customer_name}: Sidekick prepared a save play — review and decide."
        )

        pause_need_id, pause_questions = await _surface_sidekick_question(
            workspace_id, customer_id, customer_name, run_id,
            f"Approve the re-engagement email Sidekick drafted for {customer_name}?",
            f"{customer_name}: Sidekick did the research and drafted the outreach — the send is your call.",
            payload.get("source_event_id"),
            structured_type=StructuredQuestionType.PICK_ONE,
            options=[
                {"value": "approve", "label": "Approve — send it"},
                {"value": "counter", "label": "Counter — I'll adjust"},
                {"value": "hold", "label": "Hold for now"},
            ],
            question_context=question_context,
        )
        await stream_status(run_id, "running", "await_decision",
                            "Waiting for your decision on the save…", progress_pct=85,
                            customer_id=customer_id, customer_name=customer_name)
        logger.info("demo_risk_hitl_pause", run_id=run_id, need_id=pause_need_id, has_draft=bool(draft.get("body")))
        return WorkerOutcome(status="waiting", blocking_need_id=pause_need_id,
                             clarifying_questions=pause_questions)

    # Observation backstop (generic) if the worker skipped it.
    if not fstate.get(STATE_OBSERVED):
        await artifacts.record_observation(workspace_id, customer_id, text=obs_text, agent_run_id=run_id, kind="observed")

    # Follow-up: schedule whenever RISK was involved (a risk brief exists for this event),
    # whatever the primary play was — so a risk co-play on a meeting/support primary still
    # gets a follow-up; pure meeting/positive items don't.
    follow_up_id = fstate.get(STATE_FOLLOW_UP)
    if not follow_up_id and (primary == "risk" or await _risk_brief()):
        follow_up_id = await _enqueue_follow_up(
            workspace_id, customer_id, customer_name, 3,
            "Check whether the customer re-engaged after the save play.",
            source_event_id=payload.get("source_event_id"),
        )

    # Memory consolidation: fold this event into the account's long-term memory. Best-effort.
    consolidated = None
    try:
        from ..memory.ingest import consolidate_account_memory
        await stream_status(run_id, "running", "consolidate_memory",
                            "Updating account memory…", progress_pct=95,
                            customer_id=customer_id, customer_name=customer_name)
        consolidated = await consolidate_account_memory(workspace_id, customer_id, customer_name, event_summary)
    except Exception as e:
        logger.warning("consolidate_memory_failed", run_id=run_id, error=str(e))

    return WorkerOutcome(status="done", result={
        "artifact_id": primary_id,
        "task_type": task_type,
        "primary_play": primary,
        "follow_up_task_id": follow_up_id,
        "backstopped": backstopped,
        "memory": consolidated,
    })


async def _enqueue_follow_up(workspace_id, customer_id, customer_name, days, reason,
                            source_event_id=None) -> str:
    """Enqueue a self-scheduled follow-up task `days` out. Shared by the worker tool
    and the deterministic backstop. The follow-up INHERITS the triggering event id so
    its surfaced Need carries a non-null sourceEventId (dedupe + cleanup work)."""
    from datetime import datetime, timezone, timedelta
    try:
        d = int(days)
    except (TypeError, ValueError):
        d = 3
    d = max(1, d)  # follow-ups are never immediate (avoids same-drain re-claim loops)
    when = (datetime.now(timezone.utc) + timedelta(days=d)).isoformat()
    return await AgentTaskRepository(workspace_id).enqueue(
        "follow_up", customer_id=customer_id, trigger_type="play",
        priority=50, scheduled_for=when,
        payload={
            "reason": reason,
            "summary": f"Follow up on {customer_name}: {reason}",
            "source_event_id": source_event_id,
        },
    )


async def _run_play_standalone(play, workspace_id, customer_id, customer_name, run_id, payload) -> None:
    """Run a play agent directly (backstop) with a fresh session seeded from the payload."""
    from ..runtime.services import get_session_service
    session_service = get_session_service()
    state = initial_state(
        run_id=run_id, task_id="backstop", workspace_id=workspace_id,
        customer_id=customer_id, customer_name=customer_name, trigger_type="play", payload=payload,
    )
    state["meeting_title"] = payload.get("meeting_title", "the upcoming meeting")  # for the meeting writer
    state["task_summary"] = payload.get("summary") or payload.get("evidence") or payload.get("sentence") or "assess and act"
    session = await session_service.create_session(app_name=APP_NAME, user_id=workspace_id, state=state)
    runner = build_runner(play)
    msg = types.Content(role="user", parts=[types.Part(text=f"Run the play for {customer_name}.")])
    async for _e in runner.run_async(user_id=workspace_id, session_id=session.id, new_message=msg, run_config=default_run_config()):
        pass

"""
@sidekick huddle responder.

When a huddle message @-mentions "sidekick", a `huddle_reply` AgentTask is enqueued
(`request_sidekick_huddle_reply`). The worker handles it deterministically (no play
dispatch needed): read the huddle thread + customer context, generate a concise,
on-voice internal answer, and post it back as an AGENT-authored HuddleMessage.

This is the orchestrator "pulled into the room" — same queue/worker spine, a focused
handler. Bounded to answering in the huddle; it does not take customer-facing action.
"""

import json

from google.genai import types

from core.logging import get_logger
from core.model_config import get_model, ModelUseCase
from db.dataconnect_client import get_dataconnect_client

logger = get_logger("HuddleResponder")


async def request_sidekick_huddle_reply(huddle_id: str) -> str | None:
    """Producer: enqueue a huddle_reply task for a huddle that @-mentioned sidekick.
    Called wherever huddle messages are posted (route/service) when "sidekick" is in
    the mentions. Returns the task id, or None if the huddle can't be resolved."""
    from .queue.repository import AgentTaskRepository
    dc = get_dataconnect_client()
    h = (await dc.execute_query("GetHuddlePublic", {"id": huddle_id})).get("huddle")
    if not h:
        logger.warning("huddle_reply_no_huddle", huddle_id=huddle_id)
        return None
    workspace_id = (h.get("workspace") or {}).get("id")
    customer = h.get("customer") or {}
    repo = AgentTaskRepository(workspace_id)
    return await repo.enqueue(
        "huddle_reply", customer_id=customer.get("id"), trigger_type="user", priority=15,
        payload={"huddle_id": huddle_id, "summary": f"@sidekick asked in a huddle for {customer.get('name','a customer')}."},
    )


def _format_messages(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        who = "Sidekick" if m.get("authorKind") == "agent" else ((m.get("authorUser") or {}).get("displayName") or "Teammate")
        lines.append(f"{who}: {m.get('body','')}")
    return "\n".join(lines) or "(no messages)"


async def handle_huddle_reply(task: dict, *, run_id: str, workspace_id: str) -> dict:
    """Deterministic huddle_reply handler: read the huddle, answer, post an agent message.
    Returns a small result dict. Best-effort; raises only on hard failure."""
    from .memory.context import assemble_context
    from .runtime.runner import APP_NAME, build_runner, default_run_config
    from .runtime.services import get_session_service
    from google.adk.agents import LlmAgent

    payload = task.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {}
    huddle_id = payload.get("huddle_id")
    dc = get_dataconnect_client()
    h = (await dc.execute_query("GetHuddlePublic", {"id": huddle_id})).get("huddle")
    if not h:
        return {"posted": False, "reason": "huddle not found"}

    customer = h.get("customer") or {}
    customer_id = customer.get("id")
    customer_name = customer.get("name") or "the customer"
    messages = h.get("huddleMessages_on_huddle") or []

    # Build account context (reuse the scoped profiles) for a grounded answer.
    profiles = await assemble_context(workspace_id, customer_id)
    context_md = "\n\n".join(v for v in profiles.values())

    agent = LlmAgent(
        name="huddle_responder",
        model=get_model(ModelUseCase.SIGNAL_ANALYSIS),
        instruction=(
            "You are Sidekick, replying INSIDE an internal team huddle (CSMs/support talking to each "
            "other, not the customer). Someone @-mentioned you. Answer their latest question concisely "
            "and usefully, grounded in the account context below. This is internal — be direct, cite "
            "what you know, and say what you don't. Do NOT draft customer-facing copy unless asked.\n\n"
            f"CUSTOMER: {customer_name}\n\n"
            f"ACCOUNT CONTEXT:\n{context_md}\n\n"
            f"HUDDLE SO FAR:\n{_format_messages(messages)}\n\n"
            "Write only your reply (no preamble)."
        ),
    )

    session_service = get_session_service()
    session = await session_service.create_session(app_name=APP_NAME, user_id=workspace_id, state={})
    runner = build_runner(agent)
    msg = types.Content(role="user", parts=[types.Part(text="Reply to the huddle.")])
    reply_text = ""
    async for event in runner.run_async(user_id=workspace_id, session_id=session.id, new_message=msg, run_config=default_run_config()):
        if event.content and event.content.parts:
            for p in event.content.parts:
                if getattr(p, "text", None):
                    reply_text = p.text

    reply_text = (reply_text or "").strip()
    if not reply_text:
        return {"posted": False, "reason": "no reply generated"}

    await dc.execute_mutation("PostHuddleMessage", {
        "huddleId": huddle_id, "authorUserId": None, "authorKind": "agent",
        "body": reply_text, "mentions": None,
    })
    logger.info("huddle_reply_posted", huddle_id=huddle_id, run_id=run_id, chars=len(reply_text))
    return {"posted": True, "huddle_id": huddle_id}

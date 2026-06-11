"""
Scoped context assembly — "know what's relevant to where you are."

Always load User + Workspace (who you are, what your company does). Load the
Customer profile ONLY when the task is about a customer. The prompt then carries
only what the situation needs — the cheapest possible always-on context.

Built on existing read tools (reused by import, never modified):
  - get_workspace_settings  → workspace graph (value prop, autonomy, maturity)
  - get_customer_info       → customer graph (lifecycle, goals, signals, commitments)

`make_context_load_callback()` returns an ADK `before_agent_callback` that writes
these compact markdown profiles into session state (User/Workspace/Customer scope
keys). `assemble_context()` is the same logic as a plain callable, so it's directly
testable without an ADK run.
"""

from typing import Any

from core.logging import get_logger

# Reused read-only tools from the working agent (sanctioned by the architecture
# doc — import the callables, never edit handoff_auto).
from agents.handoff_auto.tools.context import (
    get_workspace_settings,
    get_customer_info,
)

from ..runtime.state import (
    KEY_USER_PROFILE,
    KEY_WORKSPACE_PROFILE,
    KEY_CUSTOMER_PROFILE,
    KEY_WORKSPACE_ID,
    KEY_CUSTOMER_ID,
    KEY_CUSTOMER_NAME,
)

logger = get_logger("OrchestratorContext")


def _fmt_workspace(ws: dict[str, Any]) -> str:
    vp = (ws.get("value_proposition") or "").strip() or "(not set)"
    return (
        "## Workspace\n"
        f"- Value proposition: {vp}\n"
        f"- Autonomy mode: {ws.get('autonomy_mode', 'smart_auto')}\n"
        f"- Maturity: {'new' if ws.get('is_new_workspace') else 'established'} "
        f"({ws.get('total_plans_created', 0)} plans, {ws.get('approved_plans', 0)} approved)\n"
        f"- Guidance: {ws.get('recommendation', 'trust_patterns')}"
    )


def _fmt_user(ws: dict[str, Any]) -> str:
    # User graph (preferences / working style) is fleshed out by the Phase-2 write
    # path. For now we carry the CSM's operating posture, derived from real
    # workspace settings rather than mocked.
    return (
        "## You (CSM)\n"
        f"- Operating autonomy: {ws.get('autonomy_mode', 'smart_auto')}\n"
        f"- Pause on medium confidence: {ws.get('pause_on_medium_confidence', True)}\n"
        "- Working style: learned over time (memory write path, Phase 2)"
    )


def _fmt_customer(c: dict[str, Any]) -> str:
    goals = c.get("goals") or []
    signals = c.get("signals") or []
    commitments = c.get("commitments") or []
    goal_lines = "\n".join(f"  - {g.get('text')}" for g in goals[:6]) or "  - (none recorded)"
    arr = c.get("arr_cents")
    arr_str = f"${arr // 100:,}" if isinstance(arr, int) else "(unknown)"
    return (
        f"## Customer: {c.get('name')}\n"
        f"- Lifecycle: {c.get('lifecycle')} | Tier: {c.get('tier')} | ARR: {arr_str}\n"
        f"- Days to renewal: {c.get('days_to_renewal')}\n"
        f"- One-liner: {c.get('one_liner') or '(none)'}\n"
        f"- Open signals: {len(signals)} | Commitments: {len(commitments)}\n"
        f"- Goals:\n{goal_lines}"
    )


async def assemble_context(
    workspace_id: str,
    customer_id: str | None = None,
) -> dict[str, str]:
    """Assemble scoped profiles. Returns markdown strings keyed by scope.

    Always returns user + workspace; includes customer only when customer_id is set.
    """
    ws = await get_workspace_settings(workspace_id)
    profiles: dict[str, str] = {
        KEY_USER_PROFILE: _fmt_user(ws),
        KEY_WORKSPACE_PROFILE: _fmt_workspace(ws),
    }
    if customer_id:
        customer = await get_customer_info(customer_id, workspace_id)
        if customer and not customer.get("error"):
            profiles[KEY_CUSTOMER_PROFILE] = _fmt_customer(customer)
        else:
            logger.warning("context_customer_not_found", customer_id=customer_id)
    logger.info(
        "context_assembled",
        workspace_id=workspace_id,
        customer_in_scope=bool(customer_id),
        keys=list(profiles.keys()),
    )
    return profiles


def make_context_load_callback():
    """Return an ADK `before_agent_callback` that loads scoped profiles into state.

    Reads workspace_id / customer_id from session state, assembles profiles, and
    writes them under their scope keys. Idempotent: skips if already loaded.
    """

    async def _before_agent(callback_context):
        try:
            state = callback_context.state
            if state.get(KEY_WORKSPACE_PROFILE):
                return None  # already loaded for this session
            workspace_id = state.get(KEY_WORKSPACE_ID)
            if not workspace_id:
                return None
            customer_id = state.get(KEY_CUSTOMER_ID)
            profiles = await assemble_context(workspace_id, customer_id)
            for key, value in profiles.items():
                state[key] = value
        except Exception as e:
            logger.warning("context_load_callback_failed", error=str(e))
        return None

    return _before_agent

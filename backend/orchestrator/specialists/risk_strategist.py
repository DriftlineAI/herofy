"""
Risk strategist specialist — the judgment of the Risk/Save play.

An `LlmAgent` with a Pydantic `output_schema` (native validation, no JSON-string
parsing). Reads the Researcher's `research_summary` from state and emits a structured
`RiskSaveOutput` (risk level, what changed, evidence, save-play steps, observation)
into state under `risk_save`. No tools — pure structured reasoning, so it's reliable.
"""

from google.adk.agents import LlmAgent

from core.model_config import get_model, ModelUseCase

from .schemas import RiskSaveOutput, RiskOutreachDraft
from ..runtime.callbacks import langfuse_model_cb

RISK_SAVE_KEY = "risk_save"
RISK_OUTREACH_KEY = "risk_outreach"


def build_risk_strategist(after_agent_callback=None) -> LlmAgent:
    return LlmAgent(
        name="risk_strategist",
        model=get_model(ModelUseCase.SIGNAL_ANALYSIS),
        instruction=(
            "You are the Risk Strategist. Assess renewal/churn risk and produce a concrete "
            "save play for this customer.\n\n"
            "RESEARCH BRIEFING:\n{research_summary}\n\n"
            "WORKSPACE RISK PLAYBOOK (the team's established play, if any):\n{risk_playbook}\n\n"
            "VOICE — how we handle a customer going dark (tone/approach):\n{voice_guide}\n\n"
            "CRITIC FEEDBACK from the previous pass (revise to address it; '(first pass...)' "
            "means this is your first attempt):\n{critic_feedback}\n\n"
            "HOW TO BUILD THE PLAY:\n"
            "- If critic feedback is present above, REVISE your play to fix every point it raises.\n"
            "- If a workspace risk playbook is provided above (not '(none)'), ADAPT IT: keep its "
            "steps and their ordering as the backbone, and specialize each one to THIS customer's "
            "evidence and goals — don't invent a different play or drop their steps. You may tighten "
            "wording or add a step only if the evidence clearly demands it.\n"
            "- If it says '(none)', design 3-5 ordered steps from best practices.\n"
            "- Either way, write in the voice described above, and ground every step in the evidence "
            "— no generic advice.\n\n"
            "Produce a structured assessment: risk level, what changed (1-2 sentences), the concrete "
            "evidence, a one-line play summary, the ordered save-play steps, and one short account "
            "observation for the activity feed."
        ),
        output_schema=RiskSaveOutput,
        output_key=RISK_SAVE_KEY,
        after_agent_callback=after_agent_callback,
        after_model_callback=langfuse_model_cb,
    )


def build_risk_outreach(after_agent_callback=None) -> LlmAgent:
    """Draft the re-engagement email the save play recommends — the real artifact the CSM
    reviews and approves at the HITL pause. Reads the research + strategy already in state."""
    return LlmAgent(
        name="risk_outreach",
        model=get_model(ModelUseCase.SIGNAL_ANALYSIS),
        instruction=(
            "You draft the re-engagement email the CSM will send to a customer who has gone quiet. "
            "It must be ready to send after a quick human review.\n\n"
            "CUSTOMER: {customer_name}\n\n"
            "RESEARCH BRIEFING:\n{research_summary}\n\n"
            "SAVE ASSESSMENT + PLAY (what changed, evidence, the plan):\n{risk_save}\n\n"
            "VOICE — how we handle a customer going dark (tone/approach):\n{voice_guide}\n\n"
            "Write a short email that: acknowledges the silence lightly (no guilt-tripping), leads "
            "with THIS customer's own goal or the value they were getting, and offers one concrete, "
            "low-friction next step — a quick async check-in. Match the voice above — warm, concrete, "
            "human, no fluff. Do NOT invent facts, metrics, or dates. End with a warm one-line sign-off "
            "(e.g. 'Talk soon,'). Do NOT include bracketed placeholders like [Your Name] or [Company] — "
            "the CSM adds their own signature. Output a subject and a plain-text body."
        ),
        output_schema=RiskOutreachDraft,
        output_key=RISK_OUTREACH_KEY,
        after_agent_callback=after_agent_callback,
        after_model_callback=langfuse_model_cb,
    )

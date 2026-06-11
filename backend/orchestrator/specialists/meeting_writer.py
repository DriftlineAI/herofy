"""
Meeting writer specialist — composes a structured meeting-prep brief.

An `LlmAgent` with `output_schema=MeetingBriefOutput`. Reads the Researcher's
`research_summary` and writes the prep brief (progress narrative, talking points,
friction, value, renewal risk, expansion). Deterministic persistence
(plays/meeting_brief.py) reuses the existing `create_meeting_brief` tool to write it.
"""

from google.adk.agents import LlmAgent

from core.model_config import get_model, ModelUseCase

from .schemas import MeetingBriefOutput
from ..runtime.callbacks import langfuse_model_cb

MEETING_BRIEF_KEY = "meeting_brief"


def build_meeting_writer(after_agent_callback=None) -> LlmAgent:
    return LlmAgent(
        name="meeting_writer",
        model=get_model(ModelUseCase.SIGNAL_ANALYSIS),
        instruction=(
            "You are preparing a CSM for an upcoming customer meeting.\n\n"
            "CUSTOMER: {customer_name}\n"
            "MEETING: {meeting_title}\n\n"
            "RESEARCH BRIEFING:\n{research_summary}\n\n"
            "Write a tight, useful prep brief grounded ONLY in the research:\n"
            "- progress_narrative: what's happened since the last touchpoint (>= 50 chars, prose).\n"
            "- talking_points: the few things the CSM must raise (specific, not generic).\n"
            "- progress_facts: concrete bullets (milestones hit, metrics) if any.\n"
            "- friction / value_delivered / risk_to_renewal / expansion_signals: fill when the "
            "evidence supports them, else leave empty.\n"
            "- followup_email: ALWAYS include a draft recap email (subject + body). "
            "Base it on the talking points — what would a CSM send within an hour of this meeting? "
            "2-4 short paragraphs: thank-you/summary, key outcomes, agreed next steps.\n"
            "Be specific to this account; do not invent facts."
        ),
        output_schema=MeetingBriefOutput,
        output_key=MEETING_BRIEF_KEY,
        after_agent_callback=after_agent_callback,
        after_model_callback=langfuse_model_cb,
    )

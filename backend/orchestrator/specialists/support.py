"""
Support specialists — a support-rep lens, not a CSM lens.

`TechnicalTriage` decides whether the signal is a technical problem and how severe /
who owns it. `SupportResponder` drafts an on-voice reply. Both are tool-less `LlmAgent`s
with `output_schema` (native validation). Bounded to triage + draft + route — we do NOT
own tickets or resolve-to-close (we see the customer's description, not their system).
"""

from google.adk.agents import LlmAgent

from core.model_config import get_model, ModelUseCase

from .schemas import TechnicalTriageOutput, SupportResponseOutput, InboundClassification
from ..runtime.callbacks import langfuse_model_cb

TRIAGE_KEY = "technical_triage"
SUPPORT_RESPONSE_KEY = "support_response"
INBOUND_CLASS_KEY = "inbound_classification"


def build_inbound_classifier(after_agent_callback=None) -> LlmAgent:
    """Lane-1 classifier — reads real customer language (not regex). One structured call:
    category + sentiment + complexity. No planner, no tools — fast and cheap."""
    return LlmAgent(
        name="inbound_classifier",
        model=get_model(ModelUseCase.SIGNAL_ANALYSIS),
        instruction=(
            "You triage an inbound customer message. Read what they ACTUALLY wrote — frustrated "
            "people don't file tidy reports, they vent. 'MY GUYS CAN'T LOGIN' is technical + angry; "
            "'quick q on the export format' is a simple question + neutral.\n\n"
            "CUSTOMER: {customer_name}\n\n"
            "MESSAGE:\n{task_summary}\n\n"
            "Classify the category, the emotional charge (sentiment), and how hard it is to answer "
            "(complexity). Judge sentiment from tone and word choice, not just topic. Be honest about "
            "complexity — most messages are simple; reserve 'complex' for genuine investigation/eng work."
        ),
        output_schema=InboundClassification,
        output_key=INBOUND_CLASS_KEY,
        after_agent_callback=after_agent_callback,
        after_model_callback=langfuse_model_cb,
    )


def build_technical_triage(after_agent_callback=None) -> LlmAgent:
    return LlmAgent(
        name="technical_triage",
        model=get_model(ModelUseCase.SIGNAL_ANALYSIS),
        instruction=(
            "You are a support engineer triaging an inbound issue. Judge it from the customer's "
            "report and the account context — you do NOT have system/log access, so reason from "
            "what's described.\n\n"
            "CUSTOMER: {customer_name}\n\n"
            "RESEARCH BRIEFING:\n{research_summary}\n\n"
            "THE ISSUE:\n{task_summary}\n\n"
            "Determine: is this genuinely a technical problem (vs a question, billing, or a "
            "relationship/sentiment matter); its severity/impact; whether it likely needs "
            "engineering (a real bug/outage) rather than just a CSM answer; and any obvious interim "
            "workaround. Be concrete; don't overstate severity without evidence."
        ),
        output_schema=TechnicalTriageOutput,
        output_key=TRIAGE_KEY,
        after_agent_callback=after_agent_callback,
        after_model_callback=langfuse_model_cb,
    )


def build_support_responder(after_agent_callback=None) -> LlmAgent:
    return LlmAgent(
        name="support_responder",
        model=get_model(ModelUseCase.SIGNAL_ANALYSIS),
        instruction=(
            "You draft the reply a CSM/support rep will send to the customer about their issue. "
            "It must be ready to send after a quick human review.\n\n"
            "CUSTOMER: {customer_name}\n\n"
            "TRIAGE:\n{technical_triage}\n\n"
            "RESEARCH BRIEFING:\n{research_summary}\n\n"
            "THE ISSUE:\n{task_summary}\n\n"
            "Write a reply that: acknowledges the specific problem, sets clear expectations (what "
            "happens next, rough timing), and gives the workaround if triage found one. Match the "
            "company voice loaded in your context — warm, concrete, no fluff. Do NOT promise fixes "
            "or dates you can't back up; if engineering is involved, say it's been escalated. "
            "Output a subject and body."
        ),
        output_schema=SupportResponseOutput,
        output_key=SUPPORT_RESPONSE_KEY,
        after_agent_callback=after_agent_callback,
        after_model_callback=langfuse_model_cb,
    )

"""
Critic specialist — self-evaluation / revision gate for plays (ADK LoopAgent).

An `LlmAgent` with a Pydantic `output_schema` (`CriticVerdict`) that judges the
strategist's proposed save play against the evidence, goal coverage, the workspace
playbook, and voice. Its verdict drives a `LoopAgent`: a deterministic gate escalates
(stops the loop) when approved, else feeds `feedback` back for one revision pass.

No tools — pure structured judgment, so it's reliable.
"""

from google.adk.agents import LlmAgent

from core.model_config import get_model, ModelUseCase

from .schemas import CriticVerdict
from ..runtime.callbacks import langfuse_model_cb

CRITIC_KEY = "critic"


def build_critic(after_agent_callback=None) -> LlmAgent:
    return LlmAgent(
        name="critic",
        model=get_model(ModelUseCase.SIGNAL_ANALYSIS),
        instruction=(
            "You are the Critic. Rigorously evaluate the proposed save play below against "
            "the research and the team's expectations. Be a tough but fair reviewer.\n\n"
            "RESEARCH BRIEFING:\n{research_summary}\n\n"
            "WORKSPACE RISK PLAYBOOK (what the team expects, if any):\n{risk_playbook}\n\n"
            "PROPOSED SAVE PLAY:\n{risk_save}\n\n"
            "Judge it on: (1) is every step grounded in the actual evidence; (2) does it serve "
            "the customer's goal/north star; (3) if a workspace playbook was provided, did it "
            "respect that play's backbone and ordering; (4) is it specific (named people, "
            "concrete actions) rather than generic; (5) right risk level.\n\n"
            "Approve ONLY if it's genuinely ready for the CSM. If not, give concrete, actionable "
            "feedback the strategist can use to revise in one pass. Provide a 1-5 score and list "
            "specific coverage gaps."
        ),
        output_schema=CriticVerdict,
        output_key=CRITIC_KEY,
        after_agent_callback=after_agent_callback,
        after_model_callback=langfuse_model_cb,
    )

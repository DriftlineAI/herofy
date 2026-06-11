"""
Handoff Auto Agent - ADK Implementation

Uses Google ADK (Agent Development Kit) for LLM orchestration.

HITL Model:
- BLOCKERS: pause_for_human_input() - Actually pauses execution (rare)
- SIDE-ASKS: add_handoff_questions(routing="sales") - Records but continues
- KICKOFF: add_handoff_questions(routing="kickoff") - Records but continues

The old implementation is preserved in ARCHIVE/ for reference.
"""

from .agent import (
    run_handoff_auto,
    resume_handoff_auto,
    check_and_resume_waiting_runs,
    handle_timed_out_runs,
    create_handoff_agent,
    HANDOFF_INSTRUCTION,
)
from .confidence import assess_confidence, should_pause
from .memory import AgentMemory

__all__ = [
    # Main entry points
    "run_handoff_auto",
    "resume_handoff_auto",
    "check_and_resume_waiting_runs",
    "handle_timed_out_runs",
    # Agent factory
    "create_handoff_agent",
    "HANDOFF_INSTRUCTION",
    # Confidence
    "assess_confidence",
    "should_pause",
    # Memory
    "AgentMemory",
]

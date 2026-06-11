"""
Handoff Agent Tools
Tools organized by function for the ADK-based handoff agent.
"""

from .context import (
    get_customer_info,
    get_workspace_settings,
    get_customer_goals,
    get_playbook_for_workspace,
    get_milestone_blocks,
    get_handbook_guide,
    recall_memory,
)
from .artifacts import (
    set_primary_goal,
    set_customer_goals,
    create_progress_vectors,
    create_customer_strategy,
    create_handoff_brief,
    update_handoff_brief,
    generate_onboarding_plan,
    surface_need_for_review,
    update_plan,
    create_meeting_brief,
)
from .hitl import (
    pause_for_human_input,
    add_handoff_questions,
    update_plan_from_answers,
)

__all__ = [
    # Context gathering
    "get_customer_info",
    "get_workspace_settings",
    "get_customer_goals",
    "get_playbook_for_workspace",
    "get_milestone_blocks",
    "get_handbook_guide",
    "recall_memory",
    # Artifacts
    "set_primary_goal",
    "set_customer_goals",
    "create_progress_vectors",
    "create_customer_strategy",
    "create_handoff_brief",
    "update_handoff_brief",
    "generate_onboarding_plan",
    "update_plan",
    "surface_need_for_review",
    "create_meeting_brief",
    # HITL
    "pause_for_human_input",
    "add_handoff_questions",
    "update_plan_from_answers",
]

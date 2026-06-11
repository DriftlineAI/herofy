"""
Autonomous Handoff Agent
True autonomous agent using Google ADK with FunctionTools

The LLM decides which tools to call based on context, rather than
following a hardcoded sequence. Features:
- Memory: Recalls past plans, similar customers, success patterns
- Planning: Creates execution plans before acting
- Self-evaluation: Assesses generated plan quality
- Self-healing: Recovers from failures autonomously
"""

import json
from contextvars import ContextVar
from datetime import datetime
from typing import Any

from google import genai
from google.genai import types

from config import settings
from core.logging import get_logger, bind_context, clear_context
from core.metrics import trace_tool_call, trace_agent_run, create_span
from core.types import AgentStatus, NeedType
from core.model_config import get_model, ModelUseCase
from db.dataconnect_client import get_dataconnect_client
from services.agent_run_service import AgentRunService
from services.sidekick_service import SidekickService
from services import PlanService
from tools.database_tool import (
    get_playbook,
    get_playbook_milestones,
    insert_need,
    normalize_uuid,
)
from .memory import AgentMemory
from .reasoning import (
    create_execution_plan,
    evaluate_plan_quality,
    decide_recovery_action,
    reflect_on_execution,
)
from .confidence import should_pause, assess_confidence
from core.types import (
    AgentStatus,
    NeedType,
    ConfidenceLevel,
    ClarifyingQuestion,
    QuestionType,
    AutonomyMode,
    WorkspaceAgentSettings,
)

logger = get_logger("AutonomousHandoffAgent")


# Task-local state using ContextVars (safe for concurrent async execution)
# Each asyncio task gets its own isolated copy of these values
_agent_paused: ContextVar[bool] = ContextVar("_agent_paused", default=False)
_pause_questions: ContextVar[list] = ContextVar("_pause_questions", default=[])
_current_run_id: ContextVar[str | None] = ContextVar("_current_run_id", default=None)


# =============================================================================
# Helper Functions
# =============================================================================

def _infer_question_type(q: dict[str, Any]) -> "StructuredQuestionType":
    """
    Infer the UI question type from question content when LLM sends invalid type.

    This handles cases where the LLM sends semantic types like "clarification" or
    "missing_data" instead of UI types like "freeform" or "pick_one".

    IMPORTANT: Be conservative - prefer freeform over yes_no to avoid misclassification.
    Users can always type in freeform, but yes/no is limiting (though we do provide
    a "Neither" escape hatch in the UI).

    Args:
        q: Question dict with 'question', 'field', 'options', etc.

    Returns:
        Appropriate StructuredQuestionType for UI rendering
    """
    from core.types import StructuredQuestionType
    import re

    question_text = (q.get("question") or q.get("text") or "").lower()
    field = (q.get("field") or "").lower()
    options = q.get("options") or []

    # If options are provided, it's a selection question
    if options:
        # Check if multi-select indicators
        multi_indicators = ["which", "what are", "select all", "choose", "pick"]
        if any(ind in question_text for ind in multi_indicators) and len(options) > 2:
            return StructuredQuestionType.PICK_MANY
        return StructuredQuestionType.PICK_ONE

    # CONSERVATIVE yes/no detection - only match very specific patterns
    # Questions like "Does X have Y?" or "Is X required?" are yes/no
    # Questions like "How will we know X?" or "What are the goals?" are NOT
    yes_no_patterns = [
        # "Does [subject] have/need/require [thing]?" - very specific
        r"^does\s+\w+\s+(have|need|require|support|use|want)",
        # "Is [thing] required/needed/enabled?" - checking a boolean state
        r"^is\s+\w+\s+(required|needed|enabled|disabled|available|supported|necessary)\??$",
        # "Do they/you need [specific thing]?" - asking about requirement
        r"^do\s+(they|you|we)\s+(need|require|have|want)\s+\w+",
        # "Are there any [things]?" - existence check
        r"^are\s+there\s+(any|existing)",
        # "Will [thing] be [state]?" - NOT "will we know" type questions
        r"^will\s+(this|it|the\s+\w+)\s+be\s+(required|needed|used)",
    ]
    for pattern in yes_no_patterns:
        if re.search(pattern, question_text):
            return StructuredQuestionType.YES_NO

    # Check field name hints - only very specific boolean field names
    boolean_fields = ["requires_sso", "needs_integration", "has_sso", "sso_required", "integration_required"]
    if field in boolean_fields:
        return StructuredQuestionType.YES_NO

    # Default to freeform - safer for open-ended questions
    return StructuredQuestionType.FREEFORM


def _extract_linked_pages_content(linked_pages_json: str | None) -> str | None:
    """
    Extract and combine content from linked pages JSON.

    Args:
        linked_pages_json: JSON string of linked pages array

    Returns:
        Combined content from all linked pages with titles, or None if no content
    """
    if not linked_pages_json:
        return None

    try:
        linked_pages = json.loads(linked_pages_json)
        if not isinstance(linked_pages, list):
            return None

        content_parts = []
        for page in linked_pages:
            content = page.get("content")
            if content and content.strip():
                title = page.get("title", "Untitled")
                source = page.get("source", "unknown")
                content_parts.append(f"## {title} ({source})\n{content}")

        if not content_parts:
            return None

        return "\n\n---\n\n".join(content_parts)

    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(
            "linked_pages_parse_error",
            error=str(e),
        )
        return None


# =============================================================================
# Tool Definitions (Functions the LLM can call)
# =============================================================================

@trace_tool_call("get_customer_info")
async def tool_get_customer_info(customer_id: str, workspace_id: str) -> dict[str, Any]:
    """
    Get comprehensive information about a customer.

    Args:
        customer_id: The customer's UUID
        workspace_id: The workspace UUID

    Returns:
        Customer details including:
        - Basic info (name, tier, ARR, lifecycle)
        - Onboarding progress
        - Stakeholders (champions, decision makers)
        - Goals (what they're trying to achieve)
        - Current signals (health indicators)
        - Raw notes (CRM data for additional context)
        - Linked pages (content from linked Notion docs, handoff docs, etc.)
    """
    # Normalize UUIDs (LLM may strip hyphens)
    normalized_customer_id = normalize_uuid(customer_id)

    dc = get_dataconnect_client()
    customer = await dc.get_customer(normalized_customer_id)

    if not customer:
        return {"error": f"Customer {normalized_customer_id} not found"}

    # Extract stakeholders
    stakeholders = customer.get("stakeholders_on_customer", [])
    stakeholder_list = [
        {
            "name": s.get("name"),
            "email": s.get("email"),
            "role": s.get("role"),
            "status": s.get("status"),
            "sentiment": s.get("sentimentNote"),
        }
        for s in stakeholders
    ]

    # Extract goals
    goals = customer.get("goals_on_customer", [])
    goal_list = [
        {
            "text": g.get("text"),
            "status": g.get("status"),
        }
        for g in goals
    ]

    # Extract current signals (health indicators)
    signals = customer.get("signals_on_customer", [])
    signal_list = [
        {
            "kind": s.get("kind"),
            "state": s.get("state"),
            "sentence": s.get("sentence"),
            "evidence": s.get("evidenceText"),
            "next_action": s.get("nextAction"),
        }
        for s in signals
    ]

    # Extract current milestones
    milestones = customer.get("milestones_on_customer", [])
    milestone_list = [
        {
            "title": m.get("title"),
            "status": m.get("status"),
            "owner_side": m.get("ownerSide"),
            "target_date": m.get("targetDate"),
            "blocked_reason": m.get("blockedReason"),
        }
        for m in milestones
    ]

    # Extract commitments
    commitments = customer.get("commitments_on_customer", [])
    commitment_list = [
        {
            "side": c.get("side"),
            "text": c.get("text"),
            "due_label": c.get("dueLabel"),
            "status": c.get("status"),
        }
        for c in commitments
    ]

    # Extract linked pages content (from Notion, etc.)
    linked_pages_content = _extract_linked_pages_content(customer.get("linkedPages"))

    return {
        # Core info
        "id": customer.get("id"),
        "name": customer.get("name"),
        "slug": customer.get("slug"),
        "tier": customer.get("tier"),
        "arr_cents": customer.get("arrCents"),
        "lifecycle": customer.get("lifecycle"),
        "one_liner": customer.get("oneLiner"),
        # Onboarding progress
        "days_to_renewal": customer.get("daysToRenewal"),
        "onboarding_day_current": customer.get("onboardingDayCurrent"),
        "onboarding_day_total": customer.get("onboardingDayTotal"),
        "renewal_readiness": customer.get("renewalReadiness"),
        "value_realization": customer.get("valueRealizationText"),
        # Enrichment status
        "enrichment_status": customer.get("enrichmentStatus"),
        "raw_notes": customer.get("rawNotes"),
        "linked_pages": linked_pages_content,  # Content from linked Notion docs, etc.
        # Relationships
        "stakeholders": stakeholder_list,
        "goals": goal_list,
        "signals": signal_list,
        "milestones": milestone_list,
        "commitments": commitment_list,
    }


@trace_tool_call("get_playbook_for_workspace")
async def tool_get_playbook_for_workspace(
    workspace_id: str,
    arr_cents: int | None = None,
    target_days: int | None = None,
) -> dict[str, Any]:
    """
    Get the best-fit playbook for a workspace, including its milestones.

    The system uses a priority order:
    1. Workspace's own playbooks (sorted by acceptance rate) - PRIORITIZE THESE
    2. Global catalog templates - smart defaults
    3. Default playbook - last resort

    Check the `source` field in the response:
    - "workspace" = This workspace has custom playbooks (preferred!)
    - "catalog" = Using global template (adapt as needed)

    For workspace playbooks, the `learning` field shows:
    - times_used, times_accepted, times_edited, times_rejected
    - acceptance_rate > 0.7 = high confidence pattern

    Args:
        workspace_id: The workspace UUID
        arr_cents: Optional ARR in cents to help select the best playbook
        target_days: Optional target timeline in days

    Returns:
        Playbook with name, archetype, source, learning metrics, and milestones
    """
    # Normalize UUID (LLM may strip hyphens)
    normalized_workspace_id = normalize_uuid(workspace_id)

    playbook = await get_playbook(normalized_workspace_id, arr_cents, target_days)

    if "error" in playbook:
        return playbook

    return playbook


@trace_tool_call("get_milestone_blocks")
async def tool_get_milestone_blocks(category: str | None = None) -> dict[str, Any]:
    """
    Get reusable milestone blocks from the global catalog.

    Use this when you need to compose a custom plan from building blocks.
    Each block encodes institutional knowledge (typical durations, prerequisites).

    Categories:
    - kickoff: Kickoff Call, Goals Alignment
    - setup: Account Setup, User Provisioning, SSO Configuration
    - integration: CRM Integration, API Setup, Data Warehouse
    - data: Data Migration, Data Validation
    - training: Admin Training, End User Training, Self-Serve Resources
    - validation: Pilot Program, UAT Testing, Success Criteria Check
    - launch: Go-Live, Go-Live Support
    - review: 30-Day Review, Value Realization Check

    Args:
        category: Optional category filter (kickoff, setup, integration, etc.)

    Returns:
        List of milestone blocks with:
        - slug: Unique identifier (use in source field)
        - name: Display name
        - typical_days, min_days, max_days: Duration guidance
        - prerequisites: Blocks that should come before
        - category, tags: Classification
    """
    from tools.database_tool import get_milestone_blocks

    blocks = await get_milestone_blocks(category)

    return {
        "blocks": blocks,
        "count": len(blocks),
        "note": "Use block slugs in milestone source field, e.g., 'block:kickoff-call'",
    }


@trace_tool_call("get_customer_goals")
async def tool_get_customer_goals(customer_id: str, workspace_id: str) -> dict[str, Any]:
    """
    Get a customer's goals.

    Use this early in the workflow to check if goals exist.
    If has_goals is False, you should ask the human about goals
    via pause_for_human_input.

    Args:
        customer_id: The customer's UUID
        workspace_id: The workspace UUID

    Returns:
        Dictionary with:
        - has_goals: Boolean indicating if any goals exist
        - goals: List of goals with text, status, sort_order
        - goal_count: Number of goals
    """
    # Normalize UUIDs (LLM may strip hyphens)
    normalized_customer_id = normalize_uuid(customer_id)
    normalized_workspace_id = normalize_uuid(workspace_id)

    dc = get_dataconnect_client()

    try:
        result = await dc.execute_query(
            "GetCustomerGoals",
            {
                "customerId": normalized_customer_id,
                "workspaceId": normalized_workspace_id,
            },
        )

        goals = result.get("goals", [])
        goal_list = [
            {
                "id": g.get("id"),
                "text": g.get("text"),
                "status": g.get("status", "active"),
                "sort_order": g.get("sortOrder", 0),
            }
            for g in goals
        ]

        logger.info(
            "customer_goals_retrieved",
            customer_id=normalized_customer_id,
            goal_count=len(goal_list),
        )

        return {
            "has_goals": len(goal_list) > 0,
            "goals": goal_list,
            "goal_count": len(goal_list),
        }

    except Exception as e:
        logger.warning("customer_goals_query_failed", error=str(e))
        return {
            "has_goals": False,
            "goals": [],
            "goal_count": 0,
            "error": str(e),
        }


def _normalize_goal_text(text: str) -> str:
    """Normalize goal text for deduplication comparison."""
    # Lowercase, strip whitespace, remove punctuation variations
    normalized = text.lower().strip()
    # Remove common punctuation that might vary
    for char in [".", ",", "!", "?", "-", "—", "'"]:
        normalized = normalized.replace(char, "")
    # Collapse multiple spaces
    normalized = " ".join(normalized.split())
    return normalized


def _is_duplicate_goal(new_text: str, existing_goals: list[dict]) -> bool:
    """Check if a goal with similar text already exists."""
    normalized_new = _normalize_goal_text(new_text)
    for existing in existing_goals:
        existing_text = existing.get("text", "")
        normalized_existing = _normalize_goal_text(existing_text)
        # Exact match after normalization
        if normalized_new == normalized_existing:
            return True
        # Check if one contains the other (handles minor variations)
        if len(normalized_new) > 20 and len(normalized_existing) > 20:
            if normalized_new in normalized_existing or normalized_existing in normalized_new:
                return True
    return False


@trace_tool_call("set_customer_goals")
async def tool_set_customer_goals(
    workspace_id: str,
    customer_id: str,
    goals: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Set customer goals. Creates new goals from the provided list.

    Use this after receiving goal information from human input.
    Each goal is created with status 'active' by default.
    Duplicate goals (matching existing text) are skipped.

    Args:
        workspace_id: The workspace UUID
        customer_id: The customer UUID
        goals: List of goals to create. Each goal should have:
            - text: The goal description (required)
            - status: "active", "achieved", or "dropped" (optional, defaults to "active")

    Returns:
        Confirmation with count of goals created and skipped
    """
    # Normalize UUIDs (LLM may strip hyphens)
    normalized_workspace_id = normalize_uuid(workspace_id)
    normalized_customer_id = normalize_uuid(customer_id)

    dc = get_dataconnect_client()
    created_count = 0
    skipped_count = 0
    errors = []

    # Fetch existing goals for deduplication
    existing_goals = []
    try:
        goals_result = await dc.execute_query(
            "GetCustomerGoals",
            {
                "customerId": normalized_customer_id,
                "workspaceId": normalized_workspace_id,
            },
        )
        existing_goals = goals_result.get("goals", [])
    except Exception as e:
        logger.warning(
            "existing_goals_fetch_failed",
            customer_id=normalized_customer_id,
            error=str(e),
        )

    for i, goal in enumerate(goals):
        goal_text = goal.get("text", "").strip()
        if not goal_text:
            continue

        # Check for duplicates
        if _is_duplicate_goal(goal_text, existing_goals):
            logger.info(
                "goal_skipped_duplicate",
                customer_id=normalized_customer_id,
                goal_text=goal_text[:50],
            )
            skipped_count += 1
            continue

        goal_status = goal.get("status", "active")
        if goal_status not in ("active", "achieved", "dropped"):
            goal_status = "active"

        try:
            await dc.execute_mutation(
                "CreateGoalWithSource",
                {
                    "workspaceId": normalized_workspace_id,
                    "customerId": normalized_customer_id,
                    "text": goal_text,
                    "source": "Sidekick",
                    "sourceType": "ai_inferred",
                    "sortOrder": i,
                },
            )
            created_count += 1
            # Add to existing goals to prevent duplicates within same batch
            existing_goals.append({"text": goal_text})
        except Exception as e:
            errors.append(f"Goal '{goal_text[:30]}...': {str(e)}")

    logger.info(
        "customer_goals_created",
        workspace_id=normalized_workspace_id,
        customer_id=normalized_customer_id,
        created_count=created_count,
        skipped_count=skipped_count,
        error_count=len(errors),
    )

    result = {
        "status": "success" if created_count > 0 or skipped_count > 0 else "error",
        "goals_created": created_count,
        "goals_skipped_duplicate": skipped_count,
        "message": f"Created {created_count} goal(s) for customer, skipped {skipped_count} duplicate(s).",
    }

    if errors:
        result["errors"] = errors

    return result


@trace_tool_call("get_handbook_guide")
async def tool_get_handbook_guide(workspace_id: str, topic: str) -> dict[str, Any]:
    """
    Get a handbook guide/doc for a specific topic.

    Looks up handbook docs by topic keyword. If no custom guide exists
    for this workspace, returns a smart default guide.

    Topics supported:
    - "onboarding" - How we onboard customers
    - "success" - How we define success
    - "going dark" - How we define going dark

    Args:
        workspace_id: The workspace UUID
        topic: The topic to look up (e.g., "onboarding", "success")

    Returns:
        Dictionary with:
        - has_custom_guide: Boolean indicating if workspace has custom guide
        - guide_content: The guide content (custom or default)
        - guide_title: The guide title
        - is_default: True if using default guide
    """
    from .default_guides import get_default_guide_for_topic, get_onboarding_defaults_summary

    # Normalize UUID (LLM may strip hyphens)
    normalized_workspace_id = normalize_uuid(workspace_id)

    dc = get_dataconnect_client()

    # Map topic to potential handbook doc slugs
    topic_lower = topic.lower()
    slug_candidates = []

    if any(kw in topic_lower for kw in ["onboard", "implementation"]):
        slug_candidates = ["how-we-onboard-customers", "onboarding", "implementation"]
    elif any(kw in topic_lower for kw in ["success", "value"]):
        slug_candidates = ["how-we-define-success", "success-criteria", "success"]
    elif any(kw in topic_lower for kw in ["dark", "silent"]):
        slug_candidates = ["how-we-define-going-dark", "going-dark", "silence"]

    # Try to find a custom handbook doc
    for slug in slug_candidates:
        try:
            result = await dc.execute_query(
                "GetHandbookDocBySlug",
                {
                    "workspaceId": normalized_workspace_id,
                    "slug": slug,
                },
            )
            docs = result.get("handbookDocs", [])
            if docs:
                doc = docs[0]
                return {
                    "has_custom_guide": True,
                    "guide_content": doc.get("body", ""),
                    "guide_title": doc.get("title", slug),
                    "is_default": False,
                    "slug": slug,
                }
        except Exception:
            continue

    # No custom guide found - use default
    default_content = get_default_guide_for_topic(topic)

    if default_content:
        logger.info(
            "using_default_guide",
            workspace_id=normalized_workspace_id,
            topic=topic,
        )
        return {
            "has_custom_guide": False,
            "guide_content": default_content,
            "guide_title": f"Default Guide: {topic.title()}",
            "is_default": True,
            "note": "No custom guide found for this workspace. Using default guidance.",
        }

    # No default either - return summary
    return {
        "has_custom_guide": False,
        "guide_content": get_onboarding_defaults_summary(),
        "guide_title": "Default Onboarding Summary",
        "is_default": True,
        "note": f"No guide found for topic '{topic}'. Using general defaults.",
    }


@trace_tool_call("generate_onboarding_plan")
async def tool_generate_onboarding_plan(
    workspace_id: str,
    customer_id: str,
    customer_name: str,
    playbook: dict[str, Any],
    milestones: list[dict[str, Any]],
    context: str | None = None,
) -> dict[str, Any]:
    """
    Generate an AI-powered onboarding plan for a customer based on a playbook.

    Args:
        workspace_id: The workspace UUID
        customer_id: The customer UUID
        customer_name: The customer's name (for the headline)
        playbook: The playbook to base the plan on
        milestones: The milestone templates from the playbook
        context: Optional additional context about the customer

    Returns:
        Created AI plan with id, milestone_count, duration_label
    """
    # Normalize UUIDs (LLM may strip hyphens)
    normalized_workspace_id = normalize_uuid(workspace_id)
    normalized_customer_id = normalize_uuid(customer_id)

    # Check if customer has an existing handoff brief to link to
    brief_id = None
    try:
        dc = get_dataconnect_client()
        result = await dc.execute_query("GetCustomerHandoffWithPlan", {
            "customerId": normalized_customer_id
        })
        briefs = result.get("handoffBriefs", [])
        if briefs:
            brief_id = briefs[0].get("id")
            logger.info("linking_plan_to_existing_brief", brief_id=brief_id, customer_id=normalized_customer_id)
    except Exception as e:
        logger.warning("failed_to_lookup_brief", error=str(e), customer_id=normalized_customer_id)

    # PlanService uses DataConnect internally, db param is legacy
    service = PlanService(db=None, workspace_id=normalized_workspace_id)

    # Adapt milestones (simple adaptation, no LLM call here)
    adapted_milestones = await service.adapt_milestones(
        playbook_milestones=milestones,
        deal_data={},  # No deal data for existing customers
        gap_analysis={"timeline_feasible": True},  # Default
    )

    # Create the plan (linked to brief if one exists)
    plan = await service.create_plan(
        brief_id=brief_id,
        customer_id=normalized_customer_id,
        playbook=playbook,
        milestones=adapted_milestones,
        headline=f"Onboarding plan for {customer_name}",
        rationale=f"Generated from {playbook.get('name', 'default')} playbook. {context or ''}",
        handbook_version_id=None,  # Optional
    )

    return plan


@trace_tool_call("surface_need_for_review")
async def tool_surface_need_for_review(
    workspace_id: str,
    customer_id: str,
    customer_name: str,
    plan_id: str,
    milestone_count: int,
    playbook_name: str,
    quality_assessment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Surface a need in the Today queue for a CSM to review the generated plan.

    Args:
        workspace_id: The workspace UUID
        customer_id: The customer UUID
        customer_name: The customer's name
        plan_id: The generated plan's UUID
        milestone_count: Number of milestones in the plan
        playbook_name: Name of the playbook used
        quality_assessment: Optional self-evaluation results

    Returns:
        Created need with id, type, headline
    """
    # Normalize UUIDs (LLM may strip hyphens)
    normalized_workspace_id = normalize_uuid(workspace_id)
    normalized_customer_id = normalize_uuid(customer_id)
    normalized_plan_id = normalize_uuid(plan_id)

    # Build reasoning that includes quality assessment if available
    reasoning = f"Customer was added via setup wizard. Generated onboarding plan (ID: {normalized_plan_id}) requires review before activation."

    if quality_assessment:
        quality_score = quality_assessment.get("quality_score", 0)
        reasoning += f"\n\nSelf-assessment: Quality score {quality_score:.0%}."
        if quality_assessment.get("issues"):
            reasoning += f" Potential issues: {', '.join(quality_assessment['issues'][:2])}."
        if quality_assessment.get("would_approve_immediately"):
            reasoning += " Agent recommends immediate approval."

    # Get current agent run ID
    current_run_id = _current_run_id.get()

    # Link the plan to the agent run so it can be accessed via Need -> AgentRun -> Plan
    if current_run_id:
        dc = get_dataconnect_client()
        try:
            await dc.execute_mutation("SetAgentRunPlan", {
                "id": current_run_id,
                "planId": normalized_plan_id,
            })
            logger.info("linked_plan_to_agent_run", run_id=current_run_id, plan_id=normalized_plan_id)
        except Exception as e:
            logger.warning("failed_to_link_plan_to_agent_run", error=str(e), run_id=current_run_id)

    need = await insert_need(
        workspace_id=normalized_workspace_id,
        customer_id=normalized_customer_id,
        need_type=NeedType.PLAN_APPROVAL_REQUIRED.value,
        headline=f"Review onboarding plan for {customer_name}",
        lede=f"AI generated {milestone_count} milestones based on {playbook_name} playbook",
        agent_reasoning=reasoning,
        priority_rank=5,  # High priority
        agent_run_id=current_run_id,  # Link to agent run for plan access
    )

    return need


# =============================================================================
# Memory Tools (Long-term memory for learning)
# =============================================================================

@trace_tool_call("recall_memory")
async def tool_recall_memory(
    workspace_id: str,
    memory_type: str,
    customer_id: str | None = None,
    tier: str | None = None,
    arr_cents: int | None = None,
) -> dict[str, Any]:
    """
    Recall information from long-term memory.

    Args:
        workspace_id: The workspace UUID
        memory_type: Type of memory to recall ('past_plans', 'similar_customers', 'success_patterns', 'hitl_patterns')
        customer_id: Optional customer ID for filtering
        tier: Optional tier for finding similar customers
        arr_cents: Optional ARR for finding similar customers

    Returns:
        Memory context based on the type requested
    """
    memory = AgentMemory(workspace_id)

    if memory_type == "past_plans":
        plans = await memory.recall_past_plans(customer_id=customer_id)
        return {
            "type": "past_plans",
            "plans": plans,
            "summary": f"Found {len(plans)} past plans" + (f" for this customer" if customer_id else ""),
        }

    elif memory_type == "similar_customers":
        customers = await memory.recall_similar_customers(tier=tier, arr_cents=arr_cents)
        return {
            "type": "similar_customers",
            "customers": customers,
            "summary": f"Found {len(customers)} similar customers",
        }

    elif memory_type == "success_patterns":
        patterns = await memory.recall_success_patterns()
        return {
            "type": "success_patterns",
            "patterns": patterns,
            "summary": f"Found {len(patterns.get('archetype_performance', []))} archetype patterns",
        }

    elif memory_type == "hitl_patterns":
        hitl = await memory.recall_hitl_patterns()
        return {
            "type": "hitl_patterns",
            "interactions": hitl,
            "summary": f"Found {len(hitl)} past HITL interactions",
        }

    else:
        return {"error": f"Unknown memory type: {memory_type}"}


# =============================================================================
# Planning Tools (Task decomposition and self-evaluation)
# =============================================================================

@trace_tool_call("create_execution_checklist")
async def tool_create_execution_checklist(
    goal: str,
    workspace_id: str,
    customer_id: str,
    customer_name: str,
    customer_tier: str | None = None,
    arr_cents: int | None = None,
) -> dict[str, Any]:
    """
    Create YOUR internal execution checklist before taking action.

    IMPORTANT: This is YOUR internal task list for completing this agent run.
    It is NOT the customer's onboarding plan. The customer's onboarding plan
    is produced separately by `generate_onboarding_plan`.

    Your checklist should describe:
    - Which TOOLS you will call and in what order
    - What information you need to gather
    - Decision points and fallback strategies

    It should NOT describe:
    - What the customer should do
    - Onboarding milestones for the customer
    - Customer-facing deliverables

    Args:
        goal: What YOU (the agent) need to accomplish in this run
        workspace_id: The workspace UUID
        customer_id: The customer UUID
        customer_name: The customer's name (for context)
        customer_tier: Optional tier for context
        arr_cents: Optional ARR for context

    Returns:
        Your execution checklist with tasks, tool calls, and success criteria
    """
    # First gather memory context
    memory = AgentMemory(workspace_id)
    memory_context = {
        "past_plans": await memory.recall_past_plans(limit=5),
        "success_patterns": await memory.recall_success_patterns(),
    }

    if customer_tier or arr_cents:
        memory_context["similar_customers"] = await memory.recall_similar_customers(
            tier=customer_tier,
            arr_cents=arr_cents,
            limit=3,
        )

    context = {
        "workspace_id": workspace_id,
        "customer_id": customer_id,
        "customer_name": customer_name,
        "customer_tier": customer_tier,
        "arr_cents": arr_cents,
    }

    checklist = await create_execution_plan(
        goal=goal,
        context=context,
        memory_context=memory_context,
    )

    # Store the checklist in the agent run's context_snapshot so it can be retrieved later
    current_run = _current_run_id.get()
    if current_run:
        try:
            dc = get_dataconnect_client()
            run_service = AgentRunService(dc, workspace_id)
            await run_service.update_step(
                run_id=current_run,
                step_name="checklist_created",
                context_snapshot={
                    "execution_checklist": checklist,
                    "customer_id": customer_id,
                    "customer_name": customer_name,
                },
            )
            logger.info(
                "execution_checklist_stored",
                run_id=current_run,
                task_count=len(checklist.get("tasks", [])),
            )
        except Exception as e:
            logger.warning("execution_checklist_storage_failed", error=str(e))

    return checklist


@trace_tool_call("get_execution_checklist")
async def tool_get_execution_checklist(
    workspace_id: str,
) -> dict[str, Any]:
    """
    Retrieve YOUR current execution checklist.

    Call this to review your task list and see what you've completed
    vs what's still pending. Use this to stay on track with your plan.

    Args:
        workspace_id: The workspace UUID

    Returns:
        Your execution checklist with tasks and completion status
    """
    current_run = _current_run_id.get()
    if not current_run:
        return {
            "error": "No active agent run found",
            "checklist": None,
        }

    try:
        dc = get_dataconnect_client()
        run_service = AgentRunService(dc, workspace_id)
        run = await run_service.get_run(current_run)

        if not run:
            return {
                "error": f"Run {current_run} not found",
                "checklist": None,
            }

        context_snapshot = run.get("context_snapshot", {})
        checklist = context_snapshot.get("execution_checklist")

        if not checklist:
            return {
                "message": "No checklist found. Call create_execution_checklist first.",
                "checklist": None,
            }

        return {
            "checklist": checklist,
            "current_step": run.get("currentStep"),
            "message": "Review your checklist and continue with the next task.",
        }

    except Exception as e:
        logger.warning("get_execution_checklist_failed", error=str(e))
        return {
            "error": str(e),
            "checklist": None,
        }


@trace_tool_call("evaluate_generated_plan")
async def tool_evaluate_generated_plan(
    plan: dict[str, Any],
    customer_name: str,
    customer_tier: str | None = None,
    arr_cents: int | None = None,
    playbook_name: str | None = None,
    playbook_archetype: str | None = None,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """
    Self-evaluate the quality of a generated plan.

    The agent critically reviews its own output before surfacing.

    Args:
        plan: The generated plan to evaluate
        customer_name: Customer's name
        customer_tier: Customer's tier
        arr_cents: Customer's ARR
        playbook_name: Playbook used
        playbook_archetype: Playbook archetype
        workspace_id: Optional workspace for memory lookup

    Returns:
        Quality assessment with score, issues, and suggestions
    """
    customer_context = {
        "name": customer_name,
        "tier": customer_tier,
        "arr_cents": arr_cents,
    }

    playbook = {
        "name": playbook_name,
        "archetype": playbook_archetype,
    }

    # Get memory context if workspace available
    memory_context = None
    if workspace_id:
        memory = AgentMemory(workspace_id)
        memory_context = {
            "success_patterns": await memory.recall_success_patterns(),
        }

    evaluation = await evaluate_plan_quality(
        plan=plan,
        customer_context=customer_context,
        playbook=playbook,
        memory_context=memory_context,
    )

    return evaluation


# =============================================================================
# HITL Tools (Human-in-the-Loop for feedback)
# =============================================================================

@trace_tool_call("get_workspace_settings")
async def tool_get_workspace_settings(workspace_id: str) -> dict[str, Any]:
    """
    Get workspace autonomy settings and value proposition.

    Args:
        workspace_id: The workspace UUID

    Returns:
        Workspace settings including autonomy mode, plan count, and value proposition
    """
    # Normalize UUID (LLM may strip hyphens)
    normalized_workspace_id = normalize_uuid(workspace_id)

    dc = get_dataconnect_client()

    try:
        # Get workspace info including value prop
        workspace_result = await dc.execute_query("GetWorkspace", {
            "id": normalized_workspace_id,
        })
        workspace = workspace_result.get("workspace", {})
        value_prop = workspace.get("valueProp", "")

        result = await dc.execute_query("GetWorkspaceAgentSettings", {
            "workspaceId": normalized_workspace_id,
        })

        settings = result.get("workspaceAgentSettings", [])
        agent_settings = next(
            (s for s in settings if s.get("agentName") == "handoff_auto"),
            None,
        )

        # Also get plan count to know if this is a new workspace
        plans_result = await dc.execute_query("GetPastPlans", {
            "workspaceId": normalized_workspace_id,
            "limit": 10,
        })
        plans = plans_result.get("aiPlans", [])
        plan_count = len(plans)
        approved_count = sum(1 for p in plans if p.get("status") == "approved")
        # Plans with user feedback (edited or explicitly approved) are what we learn from
        plans_with_feedback = sum(
            1 for p in plans
            if p.get("status") == "approved" and p.get("humanEdited")
        )

        # Workspace is "new" until we have meaningful user feedback to learn from
        # 10 approved plans with at least 3 that were human-edited
        is_new = approved_count < 10 or plans_with_feedback < 3

        return {
            "autonomy_mode": agent_settings.get("autonomyMode", "smart_auto") if agent_settings else "smart_auto",
            "pause_on_medium_confidence": agent_settings.get("pauseOnMediumConfidence", True) if agent_settings else True,
            "total_plans_created": plan_count,
            "approved_plans": approved_count,
            "plans_with_feedback": plans_with_feedback,
            "is_new_workspace": is_new,
            "recommendation": "ask_more_questions" if is_new else "trust_patterns",
            "value_proposition": value_prop,
        }
    except Exception as e:
        logger.warning("get_workspace_settings_failed", error=str(e))
        return {
            "autonomy_mode": "smart_auto",
            "pause_on_medium_confidence": True,
            "total_plans_created": 0,
            "approved_plans": 0,
            "is_new_workspace": True,
            "recommendation": "ask_more_questions",
            "value_proposition": "",
        }


@trace_tool_call("pause_for_human_input")
async def tool_pause_for_human_input(
    workspace_id: str,
    customer_id: str,
    customer_name: str,
    questions: list[dict[str, Any]],
    reason: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Pause execution and ask the human for input with structured question types.

    Use this when:
    - Confidence is low or medium (check workspace settings first)
    - This is a new workspace (< 10 approved plans or < 3 with user edits)
    - Plan quality score is below 0.5
    - You're uncertain about customer preferences

    Args:
        workspace_id: The workspace UUID
        customer_id: The customer UUID
        customer_name: The customer's name
        questions: List of questions to ask. Each question supports:
            REQUIRED:
            - question: The question text
            - field: What data this relates to (timeline, playbook, milestones, etc.)

            OPTIONAL - Question Type (defaults to 'freeform'):
            - question_type: One of 'pick_one', 'pick_many', 'pick_person', 'slider', 'freeform', 'date', 'yes_no'

            FOR pick_one/pick_many:
            - options: List of {label, value, default?, description?}
            - allow_decide: Boolean - show "Sidekick, you decide" option
            - allow_other: Boolean - allow custom text input

            FOR pick_person:
            - people: List of {name, role, avatar_seed, signal?, signal_label?, last_contact?, stakeholder_id?}
            - allow_decide: Boolean
            - allow_manual: Boolean - allow typing a new person

            FOR slider:
            - min: Minimum value
            - max: Maximum value
            - default: Default value
            - label_low: Label for minimum (e.g., "Aggressive · 3d")
            - label_high: Label for maximum (e.g., "Patient · 21d")
            - format_template: e.g., "{value} days of silence"

            FOR yes_no:
            - yes_label: Custom "Yes" label
            - no_label: Custom "No" label
            - allow_decide: Boolean

        reason: Why you're pausing (for logging)
        context: Optional context to help the human answer

    Returns:
        Confirmation that agent is paused, with instructions
    """
    from core.types import StructuredQuestionType

    # Normalize UUIDs (LLM may strip hyphens)
    normalized_workspace_id = normalize_uuid(workspace_id)
    normalized_customer_id = normalize_uuid(customer_id)

    dc = get_dataconnect_client()
    run_service = AgentRunService(dc, normalized_workspace_id)

    # Format questions for storage with structured types
    structured_questions = []
    for q in questions:
        # Get the question type (default to freeform)
        q_type_raw = q.get("question_type", "freeform")
        try:
            structured_type = StructuredQuestionType(q_type_raw.lower())
        except (ValueError, AttributeError):
            # LLM sent invalid type (like "clarification") - infer from content
            structured_type = _infer_question_type(q)
            logger.info(
                "inferred_question_type",
                original_type=q_type_raw,
                inferred_type=structured_type.value,
                field=q.get("field"),
            )

        # Build metadata based on question type
        metadata = {}

        # Handle pick_one/pick_many options
        if structured_type in (StructuredQuestionType.PICK_ONE, StructuredQuestionType.PICK_MANY):
            if q.get("options"):
                metadata["options"] = q["options"]
            if q.get("allow_decide") is not None:
                metadata["allow_decide"] = q["allow_decide"]
            if q.get("allow_other") is not None:
                metadata["allow_other"] = q["allow_other"]
            if q.get("decide_label"):
                metadata["decide_label"] = q["decide_label"]
            if structured_type == StructuredQuestionType.PICK_MANY:
                if q.get("min_selections") is not None:
                    metadata["min_selections"] = q["min_selections"]
                if q.get("max_selections") is not None:
                    metadata["max_selections"] = q["max_selections"]

        # Handle pick_person
        elif structured_type == StructuredQuestionType.PICK_PERSON:
            if q.get("people"):
                metadata["people"] = q["people"]
            if q.get("allow_decide") is not None:
                metadata["allow_decide"] = q["allow_decide"]
            if q.get("allow_manual") is not None:
                metadata["allow_manual"] = q["allow_manual"]
            if q.get("multi_select") is not None:
                metadata["multi_select"] = q["multi_select"]

        # Handle slider
        elif structured_type == StructuredQuestionType.SLIDER:
            metadata["min"] = q.get("min", 0)
            metadata["max"] = q.get("max", 100)
            metadata["default"] = q.get("default", 50)
            if q.get("step") is not None:
                metadata["step"] = q["step"]
            if q.get("label_low"):
                metadata["label_low"] = q["label_low"]
            if q.get("label_high"):
                metadata["label_high"] = q["label_high"]
            if q.get("format_template"):
                metadata["format_template"] = q["format_template"]

        # Handle yes_no
        elif structured_type == StructuredQuestionType.YES_NO:
            if q.get("yes_label"):
                metadata["yes_label"] = q["yes_label"]
            if q.get("no_label"):
                metadata["no_label"] = q["no_label"]
            if q.get("allow_decide") is not None:
                metadata["allow_decide"] = q["allow_decide"]
            if q.get("default") is not None:
                metadata["default"] = q["default"]

        # Handle date
        elif structured_type == StructuredQuestionType.DATE:
            if q.get("min_date"):
                metadata["min_date"] = q["min_date"]
            if q.get("max_date"):
                metadata["max_date"] = q["max_date"]
            if q.get("default_date"):
                metadata["default_date"] = q["default_date"]

        # Handle freeform
        elif structured_type == StructuredQuestionType.FREEFORM:
            if q.get("multiline") is not None:
                metadata["multiline"] = q["multiline"]
            if q.get("max_length") is not None:
                metadata["max_length"] = q["max_length"]

        # Create the ClarifyingQuestion with structured type
        clarifying_q = ClarifyingQuestion(
            id=q.get("id"),
            field=q.get("field", "general"),
            question=q.get("question"),
            question_type=QuestionType.CLARIFICATION,  # Legacy type
            structured_type=structured_type,
            metadata=metadata if metadata else None,
            context=q.get("context"),
            required=q.get("required", True),
            placeholder=q.get("placeholder"),
            options=q.get("options"),  # Keep for backwards compatibility
        )
        structured_questions.append(clarifying_q)

    # Create a need for the human to answer, linked to the agent run
    need = await insert_need(
        workspace_id=normalized_workspace_id,
        customer_id=normalized_customer_id,
        need_type=NeedType.SIDEKICK_QUESTION.value,
        headline=f"Sidekick needs input for {customer_name}",
        lede=f"The AI agent has {len(questions)} question(s) before continuing.",
        agent_reasoning=f"Paused for human input: {reason}",
        priority_rank=3,  # Higher priority
        agent_run_id=_current_run_id.get(),  # Link to agent run for UI navigation
    )

    # Create a SidekickItem for visibility (nav badge, RightRail, Today queue)
    # The actual questions live in AgentRun.clarifyingQuestions - this is a summary item
    current_run = _current_run_id.get()
    if current_run:
        try:
            sidekick = SidekickService(dc, normalized_workspace_id)
            sidekick_item = await sidekick.create_asking_batch(
                customer_id=normalized_customer_id,
                agent_run_id=current_run,
                question_count=len(questions),
                reason=reason,
                need_id=need.get("id"),
            )
            logger.info(
                "sidekick_item_created_for_pause",
                sidekick_item_id=sidekick_item.get("id"),
                agent_run_id=current_run,
                question_count=len(questions),
            )
        except Exception as e:
            # Log but don't fail - SidekickItem is for visibility only
            logger.warning(
                "sidekick_item_creation_failed",
                error=str(e),
                agent_run_id=current_run,
            )

    # Update the AgentRun to paused status with structured questions
    if current_run:
        await run_service.pause_run(
            run_id=current_run,
            pause_reason=reason,
            clarifying_questions=[q.model_dump() for q in structured_questions],
            blocking_need_id=need.get("id"),
            context_snapshot=context,
        )

    # Set task-local flags to stop the agent loop
    _agent_paused.set(True)
    _pause_questions.set(structured_questions)

    logger.info(
        "agent_paused_for_input",
        workspace_id=normalized_workspace_id,
        customer_id=normalized_customer_id,
        question_count=len(questions),
        # structured_type is already a string due to use_enum_values=True in ClarifyingQuestion
        question_types=[q.structured_type or "freeform" for q in structured_questions],
        reason=reason,
        need_id=need.get("id"),
        run_id=current_run,
    )

    return {
        "status": "paused",
        "need_id": need.get("id"),
        "run_id": current_run,
        "questions": [q.model_dump() for q in structured_questions],
        "message": f"Agent paused. Created need {need.get('id')} for human to answer {len(questions)} question(s).",
        "instructions": "The agent will resume automatically when the human provides answers via the Today queue.",
    }


@trace_tool_call("create_handoff_brief")
async def tool_create_handoff_brief(
    workspace_id: str,
    customer_id: str | None,
    customer_name: str,
    body: str | None = None,
    sales_commitments: list[dict[str, Any]] | None = None,
    technical_context: dict[str, Any] | None = None,
    reality_check_confidence: str | None = None,
    reality_check_risks: list[str] | None = None,
    day_current: int | None = None,
    day_total: int | None = None,
    notion_deal_id: str | None = None,
) -> dict[str, Any]:
    """
    Create a Handoff Brief document summarizing the sales handoff.

    PREFERRED: Pass a markdown `body` with the complete brief.
    The body should be a well-structured markdown document containing:
    - Customer overview
    - Sales commitments
    - Technical context
    - Timeline
    - Risks and concerns

    Call this BEFORE asking questions to ensure the brief exists for review.

    Args:
        workspace_id: The workspace UUID
        customer_id: The customer UUID (optional if not yet created)
        customer_name: The customer's name (for logging)
        body: PREFERRED - Complete markdown document with all handoff details
        sales_commitments: Legacy - List of promises/commitments from sales
        technical_context: Legacy - Technical requirements, integrations
        reality_check_confidence: Your confidence level (high/medium/low)
        reality_check_risks: Legacy - List of identified risks
        day_current: Current day in onboarding timeline
        day_total: Total planned onboarding days
        notion_deal_id: Original Notion page ID if from Notion

    Returns:
        Created brief with ID
    """
    # Normalize UUIDs (LLM may strip hyphens)
    normalized_workspace_id = normalize_uuid(workspace_id)
    normalized_customer_id = normalize_uuid(customer_id)

    dc = get_dataconnect_client()

    # Get handbook version for audit trail
    from tools.database_tool import get_handbook_version
    handbook = await get_handbook_version(workspace_id)
    handbook_version_id = handbook.get("id") if handbook else None

    # If no handbook version, create a placeholder ID
    if not handbook_version_id:
        from uuid import uuid4
        handbook_version_id = str(uuid4())
        logger.warning("no_handbook_version_for_brief", workspace_id=workspace_id)

    try:
        await dc.execute_mutation(
            "CreateHandoffBrief",
            {
                "workspaceId": normalized_workspace_id,
                "customerId": normalized_customer_id,
                "body": body,  # Markdown body (preferred)
                "dayCurrent": day_current,
                "dayTotal": day_total,
                "salesCommitments": json.dumps(sales_commitments) if sales_commitments else None,
                "technicalContext": json.dumps(technical_context) if technical_context else None,
                "realityCheckConfidence": reality_check_confidence,
                "realityCheckRisks": json.dumps(reality_check_risks) if reality_check_risks else None,
                "status": "draft",
                "notionDealId": notion_deal_id,
                "notionDealUrl": f"https://notion.so/{notion_deal_id.replace('-', '')}" if notion_deal_id else None,
                "handbookVersionId": handbook_version_id,
                "model": get_model(ModelUseCase.HANDOFF_BRIEF),
                "promptVersion": "autonomous_v2",  # Updated version for markdown body
            },
        )

        # Query back to get the ID (DataConnect insert doesn't return ID directly)
        # Use a query to get the most recent brief for this customer
        # Note: Query only takes customerId, not workspaceId
        result = await dc.execute_query(
            "GetLatestHandoffBriefForCustomer",
            {
                "customerId": normalized_customer_id,
            },
        )

        briefs = result.get("handoffBriefs", [])
        brief_id = briefs[0]["id"] if briefs else None

        logger.info(
            "handoff_brief_created",
            workspace_id=normalized_workspace_id,
            customer_id=normalized_customer_id,
            customer_name=customer_name,
            brief_id=brief_id,
        )

        return {
            "status": "created",
            "brief_id": brief_id,
            "message": f"Handoff brief created for {customer_name}. It captures sales commitments, technical context, and reality check.",
            "can_update_later": True,
        }

    except Exception as e:
        logger.error(
            "handoff_brief_creation_failed",
            workspace_id=normalized_workspace_id,
            customer_id=normalized_customer_id,
            error=str(e),
        )
        return {
            "status": "error",
            "error": str(e),
            "message": "Failed to create handoff brief. Continuing without it.",
        }


@trace_tool_call("update_handoff_brief")
async def tool_update_handoff_brief(
    brief_id: str,
    sales_commitments: list[dict[str, Any]] | None = None,
    technical_context: dict[str, Any] | None = None,
    reality_check_confidence: str | None = None,
    reality_check_risks: list[str] | None = None,
    day_current: int | None = None,
    day_total: int | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """
    Update an existing Handoff Brief with new information.

    Call this after receiving answers from humans to update the brief
    with clarified information.

    Args:
        brief_id: The brief's UUID
        sales_commitments: Updated list of commitments
        technical_context: Updated technical context
        reality_check_confidence: Updated confidence level
        reality_check_risks: Updated risks list
        day_current: Updated current day
        day_total: Updated total days
        status: New status (draft, confirmed, needs_correction)

    Returns:
        Update confirmation
    """
    dc = get_dataconnect_client()

    try:
        await dc.execute_mutation(
            "UpdateHandoffBrief",
            {
                "id": brief_id,
                "dayCurrent": day_current,
                "dayTotal": day_total,
                "salesCommitments": json.dumps(sales_commitments) if sales_commitments else None,
                "technicalContext": json.dumps(technical_context) if technical_context else None,
                "realityCheckConfidence": reality_check_confidence,
                "realityCheckRisks": json.dumps(reality_check_risks) if reality_check_risks else None,
                "status": status,
            },
        )

        logger.info(
            "handoff_brief_updated",
            brief_id=brief_id,
            status=status,
        )

        return {
            "status": "updated",
            "brief_id": brief_id,
            "message": "Handoff brief updated successfully.",
        }

    except Exception as e:
        logger.error(
            "handoff_brief_update_failed",
            brief_id=brief_id,
            error=str(e),
        )
        return {
            "status": "error",
            "error": str(e),
        }


# =============================================================================
# Tool Schemas for Gemini
# =============================================================================

TOOLS = [
    types.Tool(
        function_declarations=[
            # Core workflow tools
            types.FunctionDeclaration(
                name="get_customer_info",
                description="Get information about a customer including name, tier, ARR, and lifecycle stage",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "customer_id": types.Schema(type=types.Type.STRING, description="The customer's UUID"),
                        "workspace_id": types.Schema(type=types.Type.STRING, description="The workspace UUID"),
                    },
                    required=["customer_id", "workspace_id"],
                ),
            ),
            types.FunctionDeclaration(
                name="get_playbook_for_workspace",
                description="Get the best-fit onboarding playbook for a workspace, including milestone templates. If no playbook exists, returns an error - in that case you should ask the human for guidance via pause_for_human_input.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "workspace_id": types.Schema(type=types.Type.STRING, description="The workspace UUID"),
                        "arr_cents": types.Schema(type=types.Type.INTEGER, description="Optional ARR in cents to help select playbook"),
                    },
                    required=["workspace_id"],
                ),
            ),
            # Goals tools (customer objectives)
            types.FunctionDeclaration(
                name="get_customer_goals",
                description="Get a customer's goals. Call this early to check if goals exist. If has_goals is False, you should gather goals from the human via pause_for_human_input.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "customer_id": types.Schema(type=types.Type.STRING, description="The customer UUID"),
                        "workspace_id": types.Schema(type=types.Type.STRING, description="The workspace UUID"),
                    },
                    required=["customer_id", "workspace_id"],
                ),
            ),
            types.FunctionDeclaration(
                name="set_customer_goals",
                description="Set customer goals after receiving goal information from human input. Creates new goals for the customer.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "workspace_id": types.Schema(type=types.Type.STRING, description="The workspace UUID"),
                        "customer_id": types.Schema(type=types.Type.STRING, description="The customer UUID"),
                        "goals": types.Schema(
                            type=types.Type.ARRAY,
                            items=types.Schema(
                                type=types.Type.OBJECT,
                                properties={
                                    "text": types.Schema(type=types.Type.STRING, description="The goal description"),
                                    "status": types.Schema(type=types.Type.STRING, description="Status: 'active', 'achieved', or 'dropped'"),
                                },
                            ),
                            description="List of goals to create",
                        ),
                    },
                    required=["workspace_id", "customer_id", "goals"],
                ),
            ),
            # Handbook guide tool (workspace documentation)
            types.FunctionDeclaration(
                name="get_handbook_guide",
                description="Get a handbook guide/doc for a specific topic. Returns custom guide if configured, or smart defaults otherwise. Topics: 'onboarding', 'success', 'going dark'.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "workspace_id": types.Schema(type=types.Type.STRING, description="The workspace UUID"),
                        "topic": types.Schema(type=types.Type.STRING, description="The topic to look up (e.g., 'onboarding', 'success', 'going dark')"),
                    },
                    required=["workspace_id", "topic"],
                ),
            ),
            types.FunctionDeclaration(
                name="generate_onboarding_plan",
                description="Generate an AI-powered onboarding plan for a customer based on a playbook",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "workspace_id": types.Schema(type=types.Type.STRING, description="The workspace UUID"),
                        "customer_id": types.Schema(type=types.Type.STRING, description="The customer UUID"),
                        "customer_name": types.Schema(type=types.Type.STRING, description="The customer's name"),
                        "playbook": types.Schema(type=types.Type.OBJECT, description="The playbook object"),
                        "milestones": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.OBJECT), description="Milestone templates from playbook"),
                        "context": types.Schema(type=types.Type.STRING, description="Optional additional context from memory/planning"),
                    },
                    required=["workspace_id", "customer_id", "customer_name", "playbook", "milestones"],
                ),
            ),
            types.FunctionDeclaration(
                name="surface_need_for_review",
                description="Surface a need in the Today queue for CSM to review the generated onboarding plan. Include quality assessment if available.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "workspace_id": types.Schema(type=types.Type.STRING, description="The workspace UUID"),
                        "customer_id": types.Schema(type=types.Type.STRING, description="The customer UUID"),
                        "customer_name": types.Schema(type=types.Type.STRING, description="The customer's name"),
                        "plan_id": types.Schema(type=types.Type.STRING, description="The generated plan's UUID"),
                        "milestone_count": types.Schema(type=types.Type.INTEGER, description="Number of milestones"),
                        "playbook_name": types.Schema(type=types.Type.STRING, description="Name of playbook used"),
                        "quality_assessment": types.Schema(type=types.Type.OBJECT, description="Optional self-evaluation results"),
                    },
                    required=["workspace_id", "customer_id", "customer_name", "plan_id", "milestone_count", "playbook_name"],
                ),
            ),
            # Memory tools (long-term learning)
            types.FunctionDeclaration(
                name="recall_memory",
                description="Recall information from long-term memory: past plans, similar customers, success patterns, or HITL interaction history. Use this to learn from past experiences.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "workspace_id": types.Schema(type=types.Type.STRING, description="The workspace UUID"),
                        "memory_type": types.Schema(
                            type=types.Type.STRING,
                            description="Type of memory: 'past_plans', 'similar_customers', 'success_patterns', or 'hitl_patterns'",
                        ),
                        "customer_id": types.Schema(type=types.Type.STRING, description="Optional customer ID for filtering"),
                        "tier": types.Schema(type=types.Type.STRING, description="Optional tier for finding similar customers"),
                        "arr_cents": types.Schema(type=types.Type.INTEGER, description="Optional ARR for finding similar customers"),
                    },
                    required=["workspace_id", "memory_type"],
                ),
            ),
            # Planning tools (YOUR internal task decomposition - NOT the customer's onboarding plan)
            types.FunctionDeclaration(
                name="create_execution_checklist",
                description="Create YOUR internal execution checklist before taking action. This is YOUR task list of which tools to call and in what order - NOT the customer's onboarding plan. Call this FIRST to plan your approach.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "goal": types.Schema(type=types.Type.STRING, description="What YOU (the agent) need to accomplish"),
                        "workspace_id": types.Schema(type=types.Type.STRING, description="The workspace UUID"),
                        "customer_id": types.Schema(type=types.Type.STRING, description="The customer UUID"),
                        "customer_name": types.Schema(type=types.Type.STRING, description="The customer's name (for context)"),
                        "customer_tier": types.Schema(type=types.Type.STRING, description="Optional customer tier"),
                        "arr_cents": types.Schema(type=types.Type.INTEGER, description="Optional ARR in cents"),
                    },
                    required=["goal", "workspace_id", "customer_id", "customer_name"],
                ),
            ),
            types.FunctionDeclaration(
                name="get_execution_checklist",
                description="Retrieve YOUR current execution checklist to review progress and see what's next. Call this if you lose track of where you are.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "workspace_id": types.Schema(type=types.Type.STRING, description="The workspace UUID"),
                    },
                    required=["workspace_id"],
                ),
            ),
            # Self-evaluation tools (OPTIONAL - advisory only)
            types.FunctionDeclaration(
                name="evaluate_generated_plan",
                description="OPTIONAL: Self-evaluate plan quality for advisory notes. This is NOT a gate - you MUST surface the plan regardless of score. Include any concerns in the quality_assessment when calling surface_need_for_review.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "plan": types.Schema(type=types.Type.OBJECT, description="The generated plan to evaluate"),
                        "customer_name": types.Schema(type=types.Type.STRING, description="Customer's name"),
                        "customer_tier": types.Schema(type=types.Type.STRING, description="Customer's tier"),
                        "arr_cents": types.Schema(type=types.Type.INTEGER, description="Customer's ARR"),
                        "playbook_name": types.Schema(type=types.Type.STRING, description="Playbook used"),
                        "playbook_archetype": types.Schema(type=types.Type.STRING, description="Playbook archetype"),
                        "workspace_id": types.Schema(type=types.Type.STRING, description="Optional workspace for memory lookup"),
                    },
                    required=["plan", "customer_name"],
                ),
            ),
            # HITL tools (Human-in-the-Loop)
            types.FunctionDeclaration(
                name="get_workspace_settings",
                description="Get workspace autonomy settings to determine when to ask for human input. Check this EARLY to know if you should ask questions.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "workspace_id": types.Schema(type=types.Type.STRING, description="The workspace UUID"),
                    },
                    required=["workspace_id"],
                ),
            ),
            types.FunctionDeclaration(
                name="pause_for_human_input",
                description="""Pause execution and ask the human structured questions. Use when: (1) workspace settings indicate is_new_workspace=true, (2) quality score < 0.5, (3) you're uncertain about customer preferences.

Question types available:
- pick_one: Single choice from options (radio buttons). Use 'options' array with {label, value, default?, description?}. Set 'allow_decide':true to show 'Sidekick, you decide'.
- pick_many: Multiple choices (checkboxes). Same as pick_one but allows multiple selections.
- pick_person: Select a stakeholder. Use 'people' array with {name, role, avatar_seed, signal?, signal_label?, last_contact?, stakeholder_id?}. Set 'allow_manual':true to allow typing new person.
- slider: Numeric range. Use 'min', 'max', 'default', 'label_low', 'label_high', 'format_template'.
- freeform: Open text input. Use 'multiline':true for textarea. Default if no question_type specified.
- yes_no: Binary choice. Use 'yes_label', 'no_label' for custom labels.
- date: Date picker. Use 'min_date', 'max_date', 'default_date' in ISO format.

This creates a 'Sidekick Question' need in the Today queue.""",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "workspace_id": types.Schema(type=types.Type.STRING, description="The workspace UUID"),
                        "customer_id": types.Schema(type=types.Type.STRING, description="The customer UUID"),
                        "customer_name": types.Schema(type=types.Type.STRING, description="The customer's name"),
                        "questions": types.Schema(
                            type=types.Type.ARRAY,
                            items=types.Schema(type=types.Type.OBJECT),
                            description="List of questions. Each needs: question (text), field (data key), question_type (pick_one|pick_many|pick_person|slider|freeform|yes_no|date). Then add type-specific fields: options/people/min/max/etc.",
                        ),
                        "reason": types.Schema(type=types.Type.STRING, description="Why you're asking (for logging)"),
                        "context": types.Schema(type=types.Type.OBJECT, description="Optional context to help the human"),
                    },
                    required=["workspace_id", "customer_id", "customer_name", "questions", "reason"],
                ),
            ),
            # Handoff Brief tools (documentation)
            types.FunctionDeclaration(
                name="create_handoff_brief",
                description="""Create a Handoff Brief document. PREFERRED: Use the 'body' parameter with a complete markdown document.

The body should be structured like:
```markdown
# Handoff Brief: {Customer Name}

## Overview
Brief description of the customer and deal.

## Sales Commitments
- Commitment 1: details
- Commitment 2: details

## Technical Context
- Integration requirements
- Tech stack
- Constraints

## Timeline
- Target go-live: X days
- Key milestones

## Risks & Concerns
- Risk 1
- Risk 2

## Confidence Assessment
Your confidence level and reasoning.
```

Call this BEFORE asking questions so the brief exists for review.""",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "workspace_id": types.Schema(type=types.Type.STRING, description="The workspace UUID"),
                        "customer_id": types.Schema(type=types.Type.STRING, description="The customer UUID"),
                        "customer_name": types.Schema(type=types.Type.STRING, description="The customer's name"),
                        "body": types.Schema(type=types.Type.STRING, description="PREFERRED: Complete markdown document with all handoff details"),
                        "day_total": types.Schema(type=types.Type.INTEGER, description="Total planned onboarding days"),
                        "reality_check_confidence": types.Schema(type=types.Type.STRING, description="Your confidence: 'high', 'medium', or 'low'"),
                    },
                    required=["workspace_id", "customer_name", "body"],
                ),
            ),
            types.FunctionDeclaration(
                name="update_handoff_brief",
                description="Update an existing Handoff Brief with new information after receiving human answers.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "brief_id": types.Schema(type=types.Type.STRING, description="The brief's UUID"),
                        "sales_commitments": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.OBJECT), description="Updated commitments"),
                        "technical_context": types.Schema(type=types.Type.OBJECT, description="Updated technical context"),
                        "reality_check_confidence": types.Schema(type=types.Type.STRING, description="Updated confidence level"),
                        "reality_check_risks": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING), description="Updated risks"),
                        "day_current": types.Schema(type=types.Type.INTEGER, description="Updated current day"),
                        "day_total": types.Schema(type=types.Type.INTEGER, description="Updated total days"),
                        "status": types.Schema(type=types.Type.STRING, description="New status: 'draft', 'confirmed', or 'needs_correction'"),
                    },
                    required=["brief_id"],
                ),
            ),
        ]
    )
]

# Map function names to implementations
TOOL_IMPLEMENTATIONS = {
    # Core workflow tools
    "get_customer_info": tool_get_customer_info,
    "get_playbook_for_workspace": tool_get_playbook_for_workspace,
    "get_milestone_blocks": tool_get_milestone_blocks,
    "generate_onboarding_plan": tool_generate_onboarding_plan,
    "surface_need_for_review": tool_surface_need_for_review,
    # Goals tools
    "get_customer_goals": tool_get_customer_goals,
    "set_customer_goals": tool_set_customer_goals,
    # Handbook guide tool
    "get_handbook_guide": tool_get_handbook_guide,
    # Memory tools
    "recall_memory": tool_recall_memory,
    # Planning tools
    "create_execution_checklist": tool_create_execution_checklist,
    "get_execution_checklist": tool_get_execution_checklist,
    # Self-evaluation tools
    "evaluate_generated_plan": tool_evaluate_generated_plan,
    # HITL tools
    "get_workspace_settings": tool_get_workspace_settings,
    "pause_for_human_input": tool_pause_for_human_input,
    # Handoff Brief tools
    "create_handoff_brief": tool_create_handoff_brief,
    "update_handoff_brief": tool_update_handoff_brief,
}


# =============================================================================
# System Instruction
# =============================================================================

SYSTEM_INSTRUCTION = """You are an autonomous Customer Success agent for Herofy. Your job is to help onboard new customers by generating personalized onboarding plans.

You are a TRUE AUTONOMOUS AGENT with capabilities beyond simple tool execution:

## Your Capabilities

1. **Memory** - You can recall past experiences:
   - `recall_memory` with type='past_plans' - See what plans worked before
   - `recall_memory` with type='similar_customers' - Learn from similar cases
   - `recall_memory` with type='success_patterns' - Understand what gets approved fast
   - `recall_memory` with type='hitl_patterns' - See what questions needed clarification before

2. **Planning** - You can think before acting:
   - `create_execution_checklist` - Create YOUR internal task list of which tools to call and in what order
   - `get_execution_checklist` - Retrieve your checklist to review progress and next steps
   - NOTE: This is YOUR checklist, NOT the customer's onboarding plan (that's `generate_onboarding_plan`)

3. **Self-Evaluation** (Optional) - You can note concerns about your work:
   - `evaluate_generated_plan` - OPTIONAL advisory check. Always surface plan regardless of score.

4. **Human-in-the-Loop** - You can ask for human input:
   - `get_workspace_settings` - Check autonomy mode and if this is a new workspace
   - `pause_for_human_input` - Pause and ask clarifying questions

5. **Handoff Brief** - Document the handoff BEFORE asking questions:
   - `create_handoff_brief` - Create a brief capturing sales commitments, technical context, risks
   - `update_handoff_brief` - Update the brief after getting human answers

6. **Customer Goals** - Manage what the customer is trying to achieve:
   - `get_customer_goals` - Check existing goals (returns list of current goals)
   - `set_customer_goals` - Save NEW goals after getting them from human input

   **CRITICAL - Avoid Duplicate Goals:**
   - ALWAYS call `get_customer_goals` FIRST to see what already exists
   - Review the existing goals list carefully before creating new ones
   - DO NOT create goals that are identical or nearly identical to existing ones
   - DO NOT rephrase existing goals (e.g., if "Adopt analytics" exists, don't add "Successfully adopt analytics capabilities")
   - Only use `set_customer_goals` for goals that are MEANINGFULLY DIFFERENT from existing ones

7. **Handbook Guides** - Get guidance on how to handle situations:
   - `get_handbook_guide` with topic='onboarding' - How we onboard customers
   - `get_handbook_guide` with topic='success' - How we define success
   - Returns smart defaults if no custom guide exists for the workspace

8. **Playbook System** - Two-tier templates and blocks:
   - `get_playbook_for_workspace` - Get best-fit playbook (workspace first, then catalog)
     - Check `source` field: "workspace" = custom (prioritize!), "catalog" = template
     - `learning` field shows acceptance rate for workspace playbooks
   - `get_milestone_blocks` - Get reusable blocks for custom composition
     - Categories: kickoff, setup, integration, data, training, validation, launch, review
     - Use block slugs in plan source field, e.g., "block:kickoff-call"

## CRITICAL: Early Context Assessment

**At the START of your workflow, you MUST check these resources:**

1. **Workspace Settings**: Call `get_workspace_settings`
   - Check `is_new_workspace` and `autonomy_mode`
   - Check `value_proposition` - describes what product/service this workspace provides to their clients
   - Use value_proposition to understand the product context when building plans
   - If is_new_workspace=true, you'll need to gather more info

2. **Customer Goals**: Call `get_customer_goals`
   - If `has_goals` is false → You need to ask about goals
   - If `has_goals` is true → REVIEW the existing goals before asking for more
   - Goals are CRITICAL for shaping the onboarding plan
   - DO NOT ask for goals that already exist (even with slightly different wording)

3. **Playbook**: Call `get_playbook_for_workspace`
   - If returns error "No playbook found" → You're starting from scratch
   - You'll need comprehensive information from the human

4. **Handbook Guides**: Call `get_handbook_guide` with topic='onboarding'
   - Returns custom guide or smart defaults
   - Use this to inform your approach

**Track what's missing:**
- has_playbook = (playbook found, no error)
- has_goals = (from get_customer_goals)
- is_new_workspace = (from workspace settings)

## CRITICAL: Context-Aware Discovery

**BEFORE asking any questions:**
1. Call `get_customer_info` to retrieve raw_notes, linked_pages, stakeholders, goals, etc.
2. Carefully read the ENTIRE raw_notes AND linked_pages fields
3. Only ask about information that is MISSING or UNCLEAR from both sources

**Question Decision Matrix:**

| Information Needed | Skip If raw_notes OR linked_pages Contains | Question Type |
|-------------------|-------------------------------------------|---------------|
| Goals | "goals:", "objectives:", "looking to", "want to" | Confirmation (yes/no) |
| Timeline | dates, "X days", "by Q4", deadlines | Confirmation |
| Champion | name with title like "VP", "Director", "Lead" | Confirmation |
| Technical Needs | "SSO", "API", "integration", tech stack | Confirmation |

**Confirmation vs Discovery:**
- If data exists in raw_notes or linked_pages: "I found [X] in the notes. Is this accurate?" (yes_no)
- If data is missing from both: "What is [X]?" (freeform/pick_one)

**When has_playbook=false OR has_goals=false, ask only for MISSING info:**

1. **Goals** (only if not in raw_notes):
   "What are the primary goals for {customer_name}?"

2. **Timeline** (only if not in raw_notes):
   "What's the target go-live date?"

3. **Critical Milestones** (only if not in raw_notes):
   "Which capabilities are must-haves for launch?"

4. **Champion** (only if no stakeholders identified):
   "Who is the primary champion?"

**After receiving answers:**
1. Compare new goal information against existing goals (from `get_customer_goals`)
2. Only use `set_customer_goals` for goals that are MEANINGFULLY DIFFERENT from existing ones
   - Skip goals that are rephrased versions of existing goals
   - Skip goals that are subsets/supersets of existing goals
3. Use this information to generate a tailored plan
4. The approved plan becomes a learning example for future customers

## CRITICAL: Plan Generation Rules

**You must ALWAYS generate a plan, even without a perfect template match.**

When customer needs don't match available playbooks:
1. Use the CLOSEST playbook as a starting point
2. Adapt milestones to fit the customer's timeline
3. Add/remove milestones based on customer needs
4. Explain your adaptations in the rationale

**You are NEVER stuck.** If the customer needs 30 days and you only have 90-day templates:
- Compress milestones (combine related steps)
- Remove optional phases
- Parallelize where possible
- Generate a realistic 30-day plan

If the customer needs 120 days and you only have 45-day templates:
- Extend milestone durations
- Add validation phases between stages
- Include pilot programs if appropriate
- Generate a realistic 120-day plan

The template is a GUIDE, not a constraint. Never say "I can't find a template that fits."

## Playbook System: Templates, Blocks, and Learning

### How Playbooks Work

The system has a two-tier playbook architecture:

**Tier 1: Workspace Playbooks** (HIGHEST PRIORITY)
- Custom playbooks this workspace has created or adopted
- Sorted by acceptance rate (how often plans are accepted)
- The `learning` field shows: times_used, times_accepted, times_edited, times_rejected
- High acceptance rate (>70%) = this workspace prefers this pattern

**Tier 2: Global Catalog Templates**
- Smart defaults available to all workspaces
- Templates: Quick Start (14d), Standard SaaS (45d), Integration-Heavy (60d), Enterprise (90d), Extended (120d)
- Each template is composed of reusable milestone blocks

**Tier 3: Milestone Blocks** (for custom composition)
- Reusable milestone components with institutional knowledge
- Categories: kickoff, setup, integration, data, training, validation, launch, review
- Each block has: typical_days, min_days, max_days, prerequisites

### Using the Playbook Response

When you call `get_playbook_for_workspace`, check the `source` field:

```
source: "workspace" → This workspace has custom playbooks (prioritize these!)
source: "catalog"   → Using global template (adapt as needed)
```

For workspace playbooks, the `learning` field tells you:
- `acceptance_rate > 0.7` → High confidence pattern, use closely
- `acceptance_rate < 0.5` → Needs more adaptation
- `times_edited` high → Workspace often modifies this pattern

### Plan Output Format

Your plan milestones should include a `source` field:

```json
{
  "milestones": [
    {
      "title": "Kickoff Call",
      "owner_side": "us",
      "target_days": 3,
      "description": "Align on goals and timeline",
      "source": "block:kickoff-call"  // From catalog block
    },
    {
      "title": "Custom Security Review",
      "owner_side": "customer",
      "target_days": 5,
      "description": "Customer-specific requirement",
      "source": "custom"  // Created for this customer
    }
  ]
}
```

Source values:
- `block:<slug>` - From a catalog milestone block
- `template:<slug>` - From a catalog template
- `workspace` - From workspace's custom playbook
- `custom` - Created specifically for this customer

## Create the Handoff Brief EARLY

**ALWAYS create the Handoff Brief before pausing for questions.** This ensures:
- The CSM can review what sales promised even while waiting on answers
- The brief exists in the UI for the human to reference
- Context is captured even if the agent pauses

The Handoff Brief captures:
- **Sales Commitments**: What was promised during the sale
- **Technical Context**: Integrations, tech stack, constraints
- **Reality Check**: Your confidence level and identified risks
- **Timeline**: Expected onboarding duration

## Extracting Data for the Brief

When you call `get_customer_info`, you have access to TWO key content sources:

### 1. `raw_notes` - CRM Data
Contains content from the customer's CRM record:
- All rich text properties (sales commitments, technical requirements, notes, etc.)
- The full page body content

### 2. `linked_pages` - Linked Documents
Contains content from external documents linked to this customer (Notion handoff docs, etc.):
- Sales handoff documents
- Technical specifications
- Meeting notes
- Any other documents the CSM linked

**CRITICAL**: Read BOTH `raw_notes` AND `linked_pages` carefully. They likely contain answers to common questions like:
- Timeline expectations ("launch by Q4", "30 days", etc.)
- Technical requirements ("SSO required", "integrate with Salesforce", etc.)
- Stakeholder information (names, roles, emails)
- Sales commitments ("promised API access", "committed to training", etc.)
- Success criteria ("reduce manual entry by 50%", etc.)

**DO NOT ask questions whose answers are clearly stated in raw_notes or linked_pages.**

Also look for:
1. **commitments** - Any existing commitments captured by the system
2. **goals** - Customer's stated goals
3. **one_liner** - Brief description that may contain key context

From this data, populate the brief with:
- **sales_commitments**: Extract ALL promises from raw_notes and linked_pages
- **technical_context**: Extract tech details from raw_notes and linked_pages
- **reality_check_confidence**: Your confidence ("high", "medium", "low")
- **reality_check_risks**: List of identified risks
- **day_total**: Timeline if mentioned

## When to Ask Humans

**You MUST use `pause_for_human_input` when:**
1. `has_goals` is False - We need to know what the customer wants to achieve
2. `has_playbook` is False - No playbook means we need human guidance
3. `is_new_workspace` is True - We don't know this customer's preferences yet
4. `autonomy_mode` is 'supervised' - Always ask

**NEVER pause for human input after generating a plan.** The plan approval UI has a "Regenerate" button where users can provide feedback. Always surface the plan for review.

Autonomous does NOT mean never asking. It means knowing WHEN to ask - and that's BEFORE generating a plan, not after.

## Recommended Workflow

When given a customer_id and workspace_id:

**STEP 0 - CREATE YOUR INTERNAL EXECUTION CHECKLIST FIRST**
Call `create_execution_checklist` with goal="Complete onboarding setup for this customer" BEFORE doing anything else.
This is YOUR task list of which tools to call and in what order - NOT the customer's onboarding plan.
The checklist will be stored so you can reference it as you work through the steps.

**TIP**: If you lose track of where you are, call `get_execution_checklist` to review your task list.

Then execute your checklist:

1. **Gather Context** (in parallel or sequence):
   - `get_workspace_settings` → note is_new_workspace, value_proposition
   - `get_customer_info` → get raw_notes, linked_pages, stakeholders, goals
   - `get_customer_goals` → note has_goals
   - `get_playbook_for_workspace` → note has_playbook
   - `get_handbook_guide` topic='onboarding' → get approach guidance

2. **CREATE HANDOFF BRIEF** - Extract and document:
   - Read raw_notes and linked_pages CAREFULLY
   - Extract ALL sales commitments, technical context, timeline, risks
   - Call `create_handoff_brief` with COMPLETE data
   - This is the CSM's primary reference - make it thorough!

3. **Decision Point**:
   - IF (no goals OR no playbook OR new workspace) → Ask questions in ONE pause
   - ELSE → Proceed to plan generation

4. **Generate Plan**: Call `generate_onboarding_plan` with playbook and milestones

5. **Surface for Review**: Call `surface_need_for_review` immediately
   - Include quality concerns as advisory notes
   - NEVER ask more questions after generating a plan

## Important Guidelines

- **ALWAYS start with `create_execution_checklist`**: This is what makes you an autonomous agent
- **Your checklist != Customer's plan**: The checklist is YOUR task list; `generate_onboarding_plan` creates the customer's plan
- **Extract thoroughly**: Read ALL of raw_notes and linked_pages before creating the brief
- **Brief comes first**: Create the handoff brief BEFORE asking any questions
- **Ask comprehensively**: One batch of questions is better than multiple pauses
- **ALWAYS surface plans**: After generating the customer's onboarding plan, call `surface_need_for_review`

After completing (or pausing), summarize:
- Your execution checklist (what tools you called)
- Context assessment (has_goals, has_playbook, is_new_workspace)
- The Handoff Brief you created (with all extracted data)
- Whether you asked questions (and why)
- The customer's onboarding plan you created
- Quality assessment"""


# =============================================================================
# Agent Runner
# =============================================================================

@trace_agent_run("handoff_auto")
async def run_autonomous_handoff(
    workspace_id: str,
    customer_id: str,
    trigger_type: str = "setup_wizard",
    triggered_by: str | None = None,
) -> dict[str, Any]:
    """
    Run the autonomous handoff agent for a customer.

    The LLM decides which tools to call and in what order.

    Args:
        workspace_id: The workspace UUID
        customer_id: The customer UUID
        trigger_type: How this was triggered
        triggered_by: Who triggered it

    Returns:
        Result dict with status, plan_id, need_id, etc.
    """
    start_time = datetime.utcnow()
    run_id = f"auto-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    bind_context(
        run_id=run_id,
        workspace_id=workspace_id,
        customer_id=customer_id,
        agent="autonomous_handoff",
    )

    logger.info(
        "autonomous_agent_started",
        trigger_type=trigger_type,
        triggered_by=triggered_by,
    )

    # Track agent run in database
    dc = get_dataconnect_client()
    run_service = AgentRunService(dc, workspace_id)

    run = await run_service.create_run(
        agent_name="handoff_auto",
        trigger_type=trigger_type,
        triggered_by=triggered_by,
        input_params={"customer_id": customer_id},
    )
    run_id = run["id"]

    # Set task-local state for tools to access (each async task gets isolated values)
    _agent_paused.set(False)
    _pause_questions.set([])
    _current_run_id.set(run_id)

    await run_service.start_run(run_id)

    try:
        # Initialize Gemini client
        client = genai.Client(api_key=settings.gemini_api_key)

        # Initial prompt to the agent - require planning first, then execution
        user_message = f"""Process onboarding setup for:
- Workspace ID: {workspace_id}
- Customer ID: {customer_id}

## STEP 1: CREATE YOUR INTERNAL EXECUTION CHECKLIST FIRST

Call `create_execution_checklist` with goal="Complete onboarding setup for this customer" BEFORE doing anything else.

This creates YOUR task list of which tools to call - NOT the customer's onboarding plan.
The customer's onboarding plan is created later using `generate_onboarding_plan`.

## STEP 2: EXECUTE YOUR CHECKLIST

### 2.1 Gather Context
- Call `get_customer_info` → get raw_notes, linked_pages, stakeholders
- Call `get_workspace_settings` → understand the workspace
- Call `get_customer_goals` → check if goals exist
- Call `get_playbook_for_workspace` → find the best template

### 2.2 Create Handoff Brief (MARKDOWN DOCUMENT)
Extract ALL data from raw_notes and linked_pages, then call `create_handoff_brief` with a `body` parameter containing a complete markdown document:

```markdown
# Handoff Brief: [Customer Name]

## Overview
[Brief description of customer, deal size, why they bought]

## Sales Commitments
- [Commitment 1]: [details]
- [Commitment 2]: [details]

## Technical Context
- **Integrations**: [what they need to connect]
- **Tech Stack**: [their existing tools]
- **Constraints**: [timeline, security, compliance]

## Timeline
- **Target Go-Live**: [X days]
- **Key Milestones**: [critical dates]

## Stakeholders
- **Champion**: [name, role]
- **Decision Maker**: [name, role]

## Risks & Concerns
- [Risk 1]
- [Risk 2]

## Confidence Assessment
[High/Medium/Low] - [reasoning]
```

This is the PRIMARY document the CSM will use - make it COMPREHENSIVE!

### 2.3 DECISION POINT: Do You Have Enough Info?

**ASK QUESTIONS IF ANY OF THESE ARE TRUE:**
- Customer has no goals (has_goals=false)
- Critical info is MISSING from raw_notes AND linked_pages:
  - Timeline unclear
  - Success criteria undefined
  - Key stakeholder unknown
  - Technical requirements vague

→ Call `pause_for_human_input` with ALL your questions in ONE batch
→ Create the brief FIRST, then ask questions

**PROCEED TO PLAN IF:**
- Goals exist
- raw_notes or linked_pages have sufficient context
- You have enough info to make a reasonable plan

### 2.4 Generate Plan (only after you have enough info)
- Call `generate_onboarding_plan` with the playbook and milestones

### 2.5 Surface for Review
- Call `surface_need_for_review` to put it in the Today queue
- NEVER ask questions after generating a plan - use the UI's Regenerate

## CRITICAL RULES

1. START with `create_execution_checklist` - creates YOUR internal task list (not customer's plan)
2. EXTRACT thoroughly from raw_notes and linked_pages for the handoff brief
3. ASK QUESTIONS if you lack critical information
4. Ask ALL questions in ONE pause
5. GENERATE the customer's onboarding plan using `generate_onboarding_plan`
6. ALWAYS surface the customer's plan after generating it"""

        # Start the conversation
        messages = [
            types.Content(
                role="user",
                parts=[types.Part(text=user_message)],
            )
        ]

        # Result tracking
        result = {
            "run_id": run_id,
            "status": AgentStatus.RUNNING.value,
            "customer_id": customer_id,
            "plan_id": None,
            "need_id": None,
        }

        # Execution log for self-healing and reflection
        execution_log = []

        # Agent loop - let LLM decide what to do
        max_turns = 15  # Increased to allow for memory/planning steps
        consecutive_failures = 0
        max_consecutive_failures = 3

        for turn in range(max_turns):
            logger.debug(f"agent_turn", turn=turn)

            response = await client.aio.models.generate_content(
                model=get_model(ModelUseCase.PLAN_GENERATION),
                contents=messages,
                config=types.GenerateContentConfig(
                    tools=TOOLS,
                    system_instruction=SYSTEM_INSTRUCTION,
                ),
            )

            # Check if model wants to call functions
            if response.candidates[0].content.parts:
                parts = response.candidates[0].content.parts

                # Check for function calls
                function_calls = [p for p in parts if p.function_call]

                if function_calls:
                    # Add assistant response to history
                    messages.append(response.candidates[0].content)

                    # Execute all function calls
                    function_responses = []
                    for part in function_calls:
                        fc = part.function_call
                        logger.info(
                            "tool_called",
                            tool=fc.name,
                            args=dict(fc.args) if fc.args else {},
                        )

                        # Execute the tool
                        tool_fn = TOOL_IMPLEMENTATIONS.get(fc.name)
                        if tool_fn:
                            try:
                                tool_result = await tool_fn(**dict(fc.args))

                                # Track execution for reflection
                                execution_log.append({
                                    "action": fc.name,
                                    "args": dict(fc.args) if fc.args else {},
                                    "result": "success",
                                    "turn": turn,
                                })
                                consecutive_failures = 0  # Reset on success

                                # Track important results
                                if fc.name == "generate_onboarding_plan" and "id" in tool_result:
                                    result["plan_id"] = tool_result["id"]
                                elif fc.name == "surface_need_for_review" and "id" in tool_result:
                                    result["need_id"] = tool_result["id"]

                                function_responses.append(
                                    types.Part(
                                        function_response=types.FunctionResponse(
                                            name=fc.name,
                                            response={"result": tool_result},
                                        )
                                    )
                                )
                                logger.info(
                                    "tool_completed",
                                    tool=fc.name,
                                    success=True,
                                )
                            except Exception as e:
                                consecutive_failures += 1
                                execution_log.append({
                                    "action": fc.name,
                                    "args": dict(fc.args) if fc.args else {},
                                    "result": "failed",
                                    "error": str(e),
                                    "turn": turn,
                                })

                                logger.error(
                                    "tool_failed",
                                    tool=fc.name,
                                    error=str(e),
                                    consecutive_failures=consecutive_failures,
                                )

                                # Self-healing: Ask reasoning module what to do
                                if consecutive_failures >= max_consecutive_failures:
                                    recovery = await decide_recovery_action(
                                        failure=f"{fc.name} failed: {str(e)}",
                                        context={"workspace_id": workspace_id, "customer_id": customer_id},
                                        attempted_actions=[e["action"] for e in execution_log],
                                    )
                                    logger.info(
                                        "recovery_action_decided",
                                        action=recovery.get("action"),
                                        reasoning=recovery.get("reasoning"),
                                    )

                                    # Add recovery info to the error response
                                    function_responses.append(
                                        types.Part(
                                            function_response=types.FunctionResponse(
                                                name=fc.name,
                                                response={
                                                    "error": str(e),
                                                    "recovery_suggestion": recovery,
                                                },
                                            )
                                        )
                                    )

                                    if recovery.get("action") == "fail":
                                        # Stop execution
                                        result["status"] = AgentStatus.FAILED.value
                                        result["error"] = recovery.get("graceful_failure_message", str(e))
                                        break
                                else:
                                    function_responses.append(
                                        types.Part(
                                            function_response=types.FunctionResponse(
                                                name=fc.name,
                                                response={"error": str(e)},
                                            )
                                        )
                                    )
                        else:
                            function_responses.append(
                                types.Part(
                                    function_response=types.FunctionResponse(
                                        name=fc.name,
                                        response={"error": f"Unknown tool: {fc.name}"},
                                    )
                                )
                            )

                    # Add function responses to history
                    messages.append(
                        types.Content(
                            role="user",
                            parts=function_responses,
                        )
                    )

                    # Check if agent paused during function execution
                    if _agent_paused.get():
                        result["status"] = AgentStatus.WAITING_FOR_INPUT.value
                        result["paused_for_input"] = True
                        logger.info("agent_paused_after_tool_call", turn=turn)
                        break
                else:
                    # No function calls - model is done or responding with text
                    text_parts = [p for p in parts if p.text]
                    if text_parts:
                        final_message = text_parts[0].text
                        logger.info(
                            "agent_response",
                            message=final_message[:200],
                        )

                        # Check if agent paused for human input
                        if _agent_paused.get():
                            result["status"] = AgentStatus.WAITING_FOR_INPUT.value
                            result["summary"] = final_message
                            result["paused_for_input"] = True
                            logger.info(
                                "agent_paused_waiting_for_input",
                                questions=len(_pause_questions.get()),
                            )
                        # Agent completed successfully
                        elif result["plan_id"] and result["need_id"]:
                            result["status"] = AgentStatus.COMPLETED.value
                            result["summary"] = final_message
                        else:
                            # Agent didn't complete all steps
                            result["status"] = AgentStatus.FAILED.value
                            result["error"] = "Agent did not complete all required steps"
                        break
            else:
                # Empty response
                result["status"] = AgentStatus.FAILED.value
                result["error"] = "Empty response from model"
                break
        else:
            # Max turns reached
            result["status"] = AgentStatus.FAILED.value
            result["error"] = f"Max turns ({max_turns}) reached without completion"

        # Update run status
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        if result["status"] == AgentStatus.COMPLETED.value:
            # Post-execution reflection for learning
            try:
                reflection = await reflect_on_execution(
                    execution_log=execution_log,
                    outcome="success",
                    context={
                        "workspace_id": workspace_id,
                        "customer_id": customer_id,
                        "customer_tier": result.get("customer_tier"),
                        "arr_cents": result.get("arr_cents"),
                    },
                )
                result["reflection"] = reflection
                logger.info(
                    "execution_reflected",
                    patterns_learned=len(reflection.get("patterns_learned", [])),
                    confidence_for_next=reflection.get("confidence_for_next_run"),
                )
            except Exception as e:
                logger.warning("reflection_failed", error=str(e))

            await run_service.complete_run(
                run_id,
                result=result,
                customer_id=customer_id,
                plan_id=result.get("plan_id"),
            )
            logger.info(
                "autonomous_agent_completed",
                duration_ms=duration_ms,
                plan_id=result.get("plan_id"),
                need_id=result.get("need_id"),
                tools_called=len(execution_log),
            )
        elif result["status"] == AgentStatus.WAITING_FOR_INPUT.value:
            # Agent paused for human input - this is expected behavior
            logger.info(
                "autonomous_agent_paused",
                duration_ms=duration_ms,
                tools_called=len(execution_log),
                questions=len(_pause_questions.get()),
            )
            # Note: The pause_for_human_input tool already updated the AgentRun
            # to paused status via the run_service, so we don't need to do it again
        else:
            # Reflect on failure too
            try:
                reflection = await reflect_on_execution(
                    execution_log=execution_log,
                    outcome="failure",
                    context={
                        "workspace_id": workspace_id,
                        "customer_id": customer_id,
                        "error": result.get("error"),
                    },
                )
                result["reflection"] = reflection
            except Exception:
                pass  # Don't fail on reflection failure

            await run_service.fail_run(
                run_id,
                error_message=result.get("error", "Unknown error"),
            )
            logger.error(
                "autonomous_agent_failed",
                error=result.get("error"),
                duration_ms=duration_ms,
                tools_called=len(execution_log),
            )

        return result

    except Exception as e:
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        logger.exception("autonomous_agent_error", error=str(e))

        await run_service.fail_run(
            run_id,
            error_message=str(e),
        )

        return {
            "run_id": run_id,
            "status": AgentStatus.FAILED.value,
            "error": str(e),
        }

    finally:
        clear_context()


@trace_agent_run("handoff_auto_resume")
async def resume_autonomous_handoff(
    run_id: str,
    answers: dict[str, Any],
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """
    Resume a paused autonomous handoff agent with user answers.

    The agent will continue from where it left off, using the answers
    to make decisions about the onboarding plan.

    Args:
        run_id: The paused agent run UUID
        answers: User answers keyed by question field
        workspace_id: Optional workspace ID (will be looked up if not provided)

    Returns:
        Result dict with status, plan_id, need_id, etc.
    """
    start_time = datetime.utcnow()

    # Get the paused run data
    dc = get_dataconnect_client()

    run = await dc.get_agent_run(run_id)
    if not run:
        return {
            "run_id": run_id,
            "status": AgentStatus.FAILED.value,
            "error": "Run not found",
        }

    # Get workspace_id from run if not provided
    if not workspace_id:
        workspace_id = run.get("workspace", {}).get("id")
        if not workspace_id:
            return {
                "run_id": run_id,
                "status": AgentStatus.FAILED.value,
                "error": "Run has no workspace",
            }

    run_service = AgentRunService(dc, workspace_id)

    # Check run is paused
    if run["status"] not in ("waiting_for_input", "resuming"):
        return {
            "run_id": run_id,
            "status": AgentStatus.FAILED.value,
            "error": f"Run is not paused (status: {run['status']})",
        }

    bind_context(
        run_id=run_id,
        workspace_id=workspace_id,
        agent="autonomous_handoff_resume",
    )

    logger.info(
        "autonomous_agent_resuming",
        answer_count=len(answers),
    )

    # Parse context snapshot
    context_snapshot = {}
    if run.get("contextSnapshot"):
        try:
            context_snapshot = json.loads(run["contextSnapshot"])
        except (json.JSONDecodeError, TypeError):
            pass

    # Parse clarifying questions
    clarifying_questions = []
    if run.get("clarifyingQuestions"):
        try:
            clarifying_questions = json.loads(run["clarifyingQuestions"])
        except (json.JSONDecodeError, TypeError):
            pass

    # Get input params
    input_params = {}
    if run.get("inputParams"):
        try:
            input_params = json.loads(run["inputParams"])
        except (json.JSONDecodeError, TypeError):
            pass

    # Get customer_id from multiple sources (inputParams, context_snapshot, or customer relationship)
    customer_id = (
        input_params.get("customer_id") or
        context_snapshot.get("customer_id") or
        run.get("customer", {}).get("id")  # From direct customer relationship
    )
    if not customer_id:
        return {
            "run_id": run_id,
            "status": AgentStatus.FAILED.value,
            "error": "No customer_id in run context",
        }

    # Transition to resuming then running
    await run_service.resume_from_input(run_id, answers)
    await run_service.mark_running_after_resume(run_id)

    # Set task-local state for tools to access (each async task gets isolated values)
    _agent_paused.set(False)
    _pause_questions.set([])
    _current_run_id.set(run_id)

    try:
        # Initialize Gemini client
        client = genai.Client(api_key=settings.gemini_api_key)

        # Build resume prompt with context and answers
        questions_text = "\n".join([
            f"- {q.get('question', q.get('field', 'Unknown'))}"
            for q in clarifying_questions
        ])

        answers_text = "\n".join([
            f"- {field}: {answer}"
            for field, answer in answers.items()
        ])

        resume_message = f"""You previously paused for human input. Now the human has provided answers.

**Previous Context:**
- Workspace ID: {workspace_id}
- Customer ID: {customer_id}
- You were working on: {context_snapshot.get('goal', 'onboarding setup')}

**Questions you asked:**
{questions_text}

**User's answers:**
{answers_text}

**Instructions:**
Now continue from where you left off. Use the answers to make informed decisions.
- If you have enough information, proceed with generating the plan
- If the answers reveal new concerns, you may ask follow-up questions
- Remember to evaluate your work before surfacing

Continue with the onboarding workflow."""

        # Start fresh conversation with resume context
        messages = [
            types.Content(
                role="user",
                parts=[types.Part(text=resume_message)],
            )
        ]

        # Result tracking
        result = {
            "run_id": run_id,
            "status": AgentStatus.RUNNING.value,
            "customer_id": customer_id,
            "plan_id": None,
            "need_id": None,
            "resumed_from_pause": True,
        }

        # Execution log for reflection
        execution_log = []

        # Agent loop
        max_turns = 15
        consecutive_failures = 0
        max_consecutive_failures = 3

        for turn in range(max_turns):
            logger.debug(f"agent_turn", turn=turn, resumed=True)

            response = await client.aio.models.generate_content(
                model=get_model(ModelUseCase.PLAN_GENERATION),
                contents=messages,
                config=types.GenerateContentConfig(
                    tools=TOOLS,
                    system_instruction=SYSTEM_INSTRUCTION,
                ),
            )

            # Check if model wants to call functions
            if response.candidates[0].content.parts:
                parts = response.candidates[0].content.parts
                function_calls = [p for p in parts if p.function_call]

                if function_calls:
                    messages.append(response.candidates[0].content)
                    function_responses = []

                    for part in function_calls:
                        fc = part.function_call
                        logger.info("tool_called", tool=fc.name, args=dict(fc.args) if fc.args else {})

                        tool_fn = TOOL_IMPLEMENTATIONS.get(fc.name)
                        if tool_fn:
                            try:
                                tool_result = await tool_fn(**dict(fc.args))
                                execution_log.append({
                                    "action": fc.name,
                                    "result": "success",
                                    "turn": turn,
                                })
                                consecutive_failures = 0

                                if fc.name == "generate_onboarding_plan" and "id" in tool_result:
                                    result["plan_id"] = tool_result["id"]
                                elif fc.name == "surface_need_for_review" and "id" in tool_result:
                                    result["need_id"] = tool_result["id"]

                                function_responses.append(
                                    types.Part(
                                        function_response=types.FunctionResponse(
                                            name=fc.name,
                                            response={"result": tool_result},
                                        )
                                    )
                                )
                            except Exception as e:
                                consecutive_failures += 1
                                execution_log.append({
                                    "action": fc.name,
                                    "result": "failed",
                                    "error": str(e),
                                    "turn": turn,
                                })
                                logger.error("tool_failed", tool=fc.name, error=str(e))

                                if consecutive_failures >= max_consecutive_failures:
                                    recovery = await decide_recovery_action(
                                        failure=f"{fc.name} failed: {str(e)}",
                                        context={"workspace_id": workspace_id, "customer_id": customer_id},
                                        attempted_actions=[e["action"] for e in execution_log],
                                    )
                                    function_responses.append(
                                        types.Part(
                                            function_response=types.FunctionResponse(
                                                name=fc.name,
                                                response={"error": str(e), "recovery_suggestion": recovery},
                                            )
                                        )
                                    )
                                    if recovery.get("action") == "fail":
                                        result["status"] = AgentStatus.FAILED.value
                                        result["error"] = recovery.get("graceful_failure_message", str(e))
                                        break
                                else:
                                    function_responses.append(
                                        types.Part(
                                            function_response=types.FunctionResponse(
                                                name=fc.name,
                                                response={"error": str(e)},
                                            )
                                        )
                                    )
                        else:
                            function_responses.append(
                                types.Part(
                                    function_response=types.FunctionResponse(
                                        name=fc.name,
                                        response={"error": f"Unknown tool: {fc.name}"},
                                    )
                                )
                            )

                    messages.append(types.Content(role="user", parts=function_responses))

                    # Check if agent paused during function execution
                    if _agent_paused.get():
                        result["status"] = AgentStatus.WAITING_FOR_INPUT.value
                        result["paused_for_input"] = True
                        logger.info("agent_paused_after_tool_call", turn=turn)
                        break
                else:
                    # No function calls - model is done
                    text_parts = [p for p in parts if p.text]
                    if text_parts:
                        final_message = text_parts[0].text
                        logger.info("agent_response", message=final_message[:200])

                        if _agent_paused.get():
                            result["status"] = AgentStatus.WAITING_FOR_INPUT.value
                            result["summary"] = final_message
                            result["paused_for_input"] = True
                        elif result["plan_id"] and result["need_id"]:
                            result["status"] = AgentStatus.COMPLETED.value
                            result["summary"] = final_message
                        else:
                            result["status"] = AgentStatus.FAILED.value
                            result["error"] = "Agent did not complete all required steps"
                        break
            else:
                # Empty response - check if agent completed its work
                if result.get("plan_id") and result.get("need_id"):
                    # Agent surfaced need and has plan - this is valid completion
                    result["status"] = AgentStatus.COMPLETED.value
                    result["summary"] = "Agent completed: plan generated and surfaced for review"
                    logger.info(
                        "agent_completed_on_empty_response",
                        plan_id=result.get("plan_id"),
                        need_id=result.get("need_id"),
                    )
                elif _agent_paused.get():
                    result["status"] = AgentStatus.WAITING_FOR_INPUT.value
                    result["paused_for_input"] = True
                else:
                    result["status"] = AgentStatus.FAILED.value
                    result["error"] = "Empty response from model"
                break
        else:
            result["status"] = AgentStatus.FAILED.value
            result["error"] = f"Max turns ({max_turns}) reached without completion"

        # Update run status
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        if result["status"] == AgentStatus.COMPLETED.value:
            await run_service.complete_run(
                run_id,
                result=result,
                customer_id=customer_id,
                plan_id=result.get("plan_id"),
            )
            logger.info(
                "autonomous_agent_resumed_completed",
                duration_ms=duration_ms,
                plan_id=result.get("plan_id"),
                need_id=result.get("need_id"),
            )
        elif result["status"] == AgentStatus.WAITING_FOR_INPUT.value:
            logger.info("autonomous_agent_paused_again", duration_ms=duration_ms)
        else:
            await run_service.fail_run(run_id, error_message=result.get("error", "Unknown error"))
            logger.error("autonomous_agent_resume_failed", error=result.get("error"), duration_ms=duration_ms)

        return result

    except Exception as e:
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        logger.exception("autonomous_agent_resume_error", error=str(e))
        await run_service.fail_run(run_id, error_message=str(e))
        return {
            "run_id": run_id,
            "status": AgentStatus.FAILED.value,
            "error": str(e),
        }

    finally:
        clear_context()

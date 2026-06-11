"""
Context Gathering Tools
Tools for gathering context about customers, workspaces, playbooks, etc.
"""

import json
from typing import Any

from config import get_settings
from core.logging import get_logger
from db.dataconnect_client import get_dataconnect_client
from tools.database_tool import get_playbook, normalize_uuid

from ..memory import AgentMemory

logger = get_logger("HandoffTools.Context")
settings = get_settings()


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
        logger.warning("linked_pages_parse_error", error=str(e))
        return None


async def _build_engagement_health_block(
    workspace_id: str, customer_id: str
) -> dict[str, Any] | None:
    """Read recent engagement_health snapshots and shape them for the agent.

    Returns None when the metric-snapshots flag is off, on any error, or when no
    history exists yet. The score/state/direction/explanation let the agent reason
    about WHY an account is trending dark, not just that it is.
    """
    try:
        if not get_settings().metric_snapshots_enabled:
            return None

        from datetime import datetime, timedelta, timezone
        from services import metric_snapshots

        since = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
        snaps = await metric_snapshots.get_recent(
            workspace_id, customer_id, "engagement_health", since
        )
        if not snaps:
            return None

        recent = snaps[-7:]  # oldest-first; keep the last ~week of samples
        latest = recent[-1]

        # Trend direction over the recent window.
        direction = "stable"
        first_val, last_val = recent[0].get("value"), latest.get("value")
        if len(recent) >= 3 and first_val is not None and last_val is not None:
            delta = last_val - first_val
            if delta <= -0.08:
                direction = "declining"
            elif delta >= 0.08:
                direction = "improving"

        try:
            latest_inputs = json.loads(latest.get("inputs") or "{}")
        except (json.JSONDecodeError, TypeError):
            latest_inputs = {}

        return {
            "score": latest.get("value"),         # 0.0–1.0
            "state": latest.get("state"),         # ok | warn | risk
            "direction": direction,               # improving | stable | declining
            "explanation": latest_inputs.get("explanation", ""),
            # the 0-1 weighted sub-scores behind the composite
            "component_scores": latest_inputs.get("component_scores", {}),
            # the raw factors that drove each sub-score (days silent, cadence ratio, etc.)
            "factors": {
                "recency": latest_inputs.get("recency"),
                "cadence": latest_inputs.get("cadence"),
                "sentiment": latest_inputs.get("sentiment"),
            },
            "recent_scores": [
                round(s["value"], 2) for s in recent if s.get("value") is not None
            ],
            "samples": len(recent),
        }
    except Exception as e:
        logger.warning("engagement_health_context_failed", error=str(e))
        return None


async def get_customer_info(customer_id: str, workspace_id: str) -> dict[str, Any]:
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

    # Derived engagement-health trend (flag-gated; populated only once the sweep
    # heartbeat has written engagement_health snapshots). This is the going-dark
    # picture as a trend the agent can EXPLAIN, not just a point-in-time flag.
    # The key is always present (None when off / no history) — null is harmless to the LLM.
    engagement_health_block = await _build_engagement_health_block(
        workspace_id, normalized_customer_id
    )

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
        "linked_pages": linked_pages_content,
        # Relationships
        "stakeholders": stakeholder_list,
        "goals": goal_list,
        "signals": signal_list,
        "milestones": milestone_list,
        "commitments": commitment_list,
        # Derived engagement-health trend (None when the feature is off / no history yet)
        "engagement_health": engagement_health_block,
    }


async def get_workspace_settings(workspace_id: str) -> dict[str, Any]:
    """
    Get workspace autonomy settings and value proposition.

    Args:
        workspace_id: The workspace UUID

    Returns:
        Workspace settings including autonomy mode, plan count, and value proposition
    """
    normalized_workspace_id = normalize_uuid(workspace_id)

    dc = get_dataconnect_client()

    try:
        # Get workspace info including value prop
        workspace_result = await dc.execute_query(
            "GetWorkspace",
            {"id": normalized_workspace_id},
        )
        workspace = workspace_result.get("workspace", {})
        value_prop = workspace.get("valueProp", "")

        result = await dc.execute_query(
            "GetWorkspaceAgentSettings",
            {"workspaceId": normalized_workspace_id},
        )

        settings_list = result.get("workspaceAgentSettings", [])
        agent_settings = next(
            (s for s in settings_list if s.get("agentName") == "handoff_auto"),
            None,
        )

        # Also get plan count to know if this is a new workspace
        plans_result = await dc.execute_query(
            "GetPastPlans",
            {"workspaceId": normalized_workspace_id, "limit": 10},
        )
        plans = plans_result.get("aiPlans", [])
        plan_count = len(plans)
        approved_count = sum(1 for p in plans if p.get("status") == "approved")
        plans_with_feedback = sum(
            1 for p in plans if p.get("status") == "approved" and p.get("humanEdited")
        )

        is_new = approved_count < 10 or plans_with_feedback < 3

        return {
            "autonomy_mode": (
                agent_settings.get("autonomyMode", "smart_auto")
                if agent_settings
                else "smart_auto"
            ),
            "pause_on_medium_confidence": (
                agent_settings.get("pauseOnMediumConfidence", True)
                if agent_settings
                else True
            ),
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


async def get_customer_goals(customer_id: str, workspace_id: str) -> dict[str, Any]:
    """
    Get a customer's goals.

    Use this early in the workflow to check if goals exist.
    If has_goals is False, you should ask the human about goals.

    Args:
        customer_id: The customer's UUID
        workspace_id: The workspace UUID

    Returns:
        Dictionary with:
        - has_goals: Boolean indicating if any goals exist
        - goals: List of goals with text, status, sort_order
        - goal_count: Number of goals
    """
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


async def get_playbook_for_workspace(
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
    normalized_workspace_id = normalize_uuid(workspace_id)

    playbook = await get_playbook(normalized_workspace_id, arr_cents, target_days)

    if "error" in playbook:
        return playbook

    return playbook


async def get_milestone_blocks(category: str | None = None) -> dict[str, Any]:
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
    from tools.database_tool import get_milestone_blocks as db_get_milestone_blocks

    blocks = await db_get_milestone_blocks(category)

    return {
        "blocks": blocks,
        "count": len(blocks),
        "note": "Use block slugs in milestone source field, e.g., 'block:kickoff-call'",
    }


async def get_handbook_guide(workspace_id: str, topic: str) -> dict[str, Any]:
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
    from ..default_guides import get_default_guide_for_topic, get_onboarding_defaults_summary

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


async def recall_memory(
    workspace_id: str,
    memory_type: str,
    customer_id: str | None = None,
    tier: str | None = None,
    arr_cents: int | None = None,
) -> dict[str, Any]:
    """
    Recall information from long-term memory.

    Use this when patterns might apply - past similar customers often
    reveal what the workspace actually prefers.

    Args:
        workspace_id: The workspace UUID
        memory_type: Type of memory to recall:
            - 'past_plans': Previous plans and their outcomes
            - 'similar_customers': Customers with similar tier/ARR
            - 'success_patterns': What plans get approved fastest
            - 'hitl_patterns': What questions needed clarification before

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
            "summary": f"Found {len(plans)} past plans"
            + (f" for this customer" if customer_id else ""),
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

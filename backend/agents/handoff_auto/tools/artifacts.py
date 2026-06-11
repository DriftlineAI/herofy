"""
Artifact Creation Tools
Tools for creating handoff briefs, plans, goals, and surfacing needs.
"""

import json
import uuid
from typing import Any

from config import get_settings
from core.logging import get_logger
from core.model_config import get_model, ModelUseCase
from core.types import NeedType
from db.dataconnect_client import get_dataconnect_client
from tools.database_tool import insert_need, normalize_uuid

from .hitl import set_plan_id, set_need_id

logger = get_logger("HandoffTools.Artifacts")
settings = get_settings()


async def set_primary_goal(
    workspace_id: str,
    customer_id: str,
    goal_id: str,
) -> dict[str, Any]:
    """
    Mark a goal as the primary goal (Mission Objective) for a customer.

    The primary goal is the customer's north star - their main reason for buying.
    Only one goal can be primary at a time; calling this will clear any existing
    primary goal for the customer.

    Args:
        workspace_id: The workspace UUID
        customer_id: The customer UUID
        goal_id: The goal UUID to mark as primary

    Returns:
        Confirmation with the goal details
    """
    normalized_workspace_id = normalize_uuid(workspace_id)
    normalized_customer_id = normalize_uuid(customer_id)
    normalized_goal_id = normalize_uuid(goal_id)

    dc = get_dataconnect_client()

    try:
        # The mutation handles clearing existing primary and setting new one
        await dc.execute_mutation(
            "SetPrimaryGoal",
            {
                "goalId": normalized_goal_id,
                "customerId": normalized_customer_id,
            },
        )

        # Fetch the goal to return its details
        goals_result = await dc.execute_query(
            "GetCustomerGoals",
            {
                "customerId": normalized_customer_id,
                "workspaceId": normalized_workspace_id,
            },
        )
        goals = goals_result.get("goals", [])
        primary_goal = next((g for g in goals if g.get("id") == normalized_goal_id), None)

        logger.info(
            "primary_goal_set",
            workspace_id=normalized_workspace_id,
            customer_id=normalized_customer_id,
            goal_id=normalized_goal_id,
            goal_text=primary_goal.get("text", "Unknown")[:50] if primary_goal else None,
        )

        return {
            "status": "success",
            "goal_id": normalized_goal_id,
            "goal_text": primary_goal.get("text") if primary_goal else None,
            "message": f"Goal marked as primary (Mission Objective): {primary_goal.get('text', 'Unknown')[:50]}..."
            if primary_goal else "Goal marked as primary",
        }

    except Exception as e:
        logger.error(
            "set_primary_goal_failed",
            workspace_id=normalized_workspace_id,
            customer_id=normalized_customer_id,
            goal_id=normalized_goal_id,
            error=str(e),
        )
        return {
            "status": "error",
            "error": str(e),
        }


async def set_customer_goals(
    workspace_id: str,
    customer_id: str,
    goals_json: str,
) -> dict[str, Any]:
    """
    Set customer goals after receiving goal information from human input.

    IMPORTANT: Before calling this, you MUST call get_customer_goals to check
    what goals already exist. DO NOT create duplicate or near-duplicate goals.

    Args:
        workspace_id: The workspace UUID
        customer_id: The customer UUID
        goals_json: JSON string of list of goals to create, each with:
            - text: The goal description
            - status: "active", "achieved", or "dropped" (default: "active")

    Returns:
        Confirmation with created goal count
    """
    normalized_workspace_id = normalize_uuid(workspace_id)
    normalized_customer_id = normalize_uuid(customer_id)

    # Parse JSON parameter
    try:
        goals = json.loads(goals_json) if goals_json else []
    except json.JSONDecodeError as e:
        logger.error("set_goals_json_parse_error", error=str(e))
        return {"status": "error", "error": f"Invalid goals JSON: {e}"}

    dc = get_dataconnect_client()

    # First, get existing goals to avoid duplicates
    try:
        existing_result = await dc.execute_query(
            "GetCustomerGoals",
            {
                "customerId": normalized_customer_id,
                "workspaceId": normalized_workspace_id,
            },
        )
        existing_goals = existing_result.get("goals", [])
        existing_texts = {g.get("text", "").lower().strip() for g in existing_goals}
    except Exception:
        existing_texts = set()

    created_count = 0
    skipped_count = 0

    for idx, goal in enumerate(goals):
        text = goal.get("text", "").strip()
        status = goal.get("status", "active")

        if not text:
            continue

        # Check for duplicates (case-insensitive)
        if text.lower() in existing_texts:
            logger.info(
                "goal_skipped_duplicate",
                customer_id=normalized_customer_id,
                goal_text=text[:50],
            )
            skipped_count += 1
            continue

        try:
            await dc.execute_mutation(
                "CreateGoal",
                {
                    "workspaceId": normalized_workspace_id,
                    "customerId": normalized_customer_id,
                    "text": text,
                    "status": status,
                    "sortOrder": len(existing_goals) + idx,
                },
            )
            created_count += 1
            existing_texts.add(text.lower())
        except Exception as e:
            logger.warning(
                "goal_creation_failed",
                customer_id=normalized_customer_id,
                goal_text=text[:50],
                error=str(e),
            )

    logger.info(
        "customer_goals_set",
        customer_id=normalized_customer_id,
        created_count=created_count,
        skipped_count=skipped_count,
    )

    return {
        "status": "success",
        "created_count": created_count,
        "skipped_count": skipped_count,
        "message": f"Created {created_count} goal(s)"
        + (f", skipped {skipped_count} duplicate(s)" if skipped_count > 0 else ""),
    }


async def create_progress_vectors(
    workspace_id: str,
    customer_id: str,
    vectors_json: str,
) -> dict[str, Any]:
    """
    Create progress vectors to track movement toward customer goals.

    Progress vectors are abstract indicators of goal progress. Each goal should
    have 1-5 relevant vectors based on what matters for achieving that goal.

    Categories:
    - trust: Building customer confidence in us
    - risk_mitigation: De-risking scope, timeline, or technical concerns
    - stakeholder: Keeping key stakeholders (champion, CFO, IT) satisfied
    - value: Demonstrating concrete wins and ROI
    - momentum: Maintaining engagement velocity and cadence

    Call this after identifying the Mission Objective and setting goals.

    Args:
        workspace_id: The workspace UUID
        customer_id: The customer UUID
        vectors_json: JSON string of vectors list. Each vector must include:
            - goal_id: UUID of the goal this vector tracks (REQUIRED)
            - category: One of: trust, risk_mitigation, stakeholder, value, momentum (REQUIRED)
            - description: Brief description of what this vector measures (REQUIRED)
            - current_state: "ok" | "warn" | "risk" based on sales notes (REQUIRED)
            - progress: Optional 0.0-1.0 numeric progress toward unlock
            - target_progress: Optional target threshold (e.g., 0.8 for 80%)
            - target_label: Optional display label (e.g., "Day 14", "5 users active")
            - unlocks: What completing this vector enables
            - assessment_reason: Why you assigned this state

    Returns:
        Confirmation with created/skipped counts

    Example vectors_json:
        '[{"goal_id": "uuid-123", "category": "trust", "description": "Building trust with Sarah (champion)", "current_state": "ok", "assessment_reason": "Sarah responded positively to sales kickoff"}]'
    """
    normalized_workspace_id = normalize_uuid(workspace_id)
    normalized_customer_id = normalize_uuid(customer_id)

    # Parse JSON parameter
    try:
        vectors = json.loads(vectors_json) if vectors_json else []
    except json.JSONDecodeError as e:
        logger.error("create_vectors_json_parse_error", error=str(e))
        return {
            "status": "error",
            "error": f"Invalid vectors JSON: {e}",
            "hint": "Pass vectors_json as a valid JSON string array.",
        }

    if not vectors:
        return {
            "status": "error",
            "error": "Vectors array is empty",
            "hint": "Provide at least one vector with goal_id, category, description, and current_state.",
        }

    dc = get_dataconnect_client()

    # Get existing vectors to avoid duplicates (check by goal_id + category pair)
    # Each goal should have at most one vector per category
    try:
        existing_result = await dc.execute_query(
            "GetCustomerProgressVectors",
            {"customerId": normalized_customer_id},
        )
        existing_vectors = existing_result.get("progressVectors", [])
        # Create set of (goal_id, category) tuples for duplicate checking
        existing_pairs = {
            (v.get("goal", {}).get("id"), v.get("category"))
            for v in existing_vectors
        }
    except Exception:
        existing_pairs = set()

    created_count = 0
    skipped_count = 0
    errors = []

    for vector in vectors:
        goal_id = vector.get("goal_id")
        category = vector.get("category")
        description = vector.get("description", "").strip()
        current_state = vector.get("current_state")

        # Validate required fields
        if not goal_id:
            errors.append("Missing goal_id")
            skipped_count += 1
            continue
        if not category:
            errors.append(f"Missing category for vector: {description[:30]}...")
            skipped_count += 1
            continue
        if not description:
            errors.append("Missing description")
            skipped_count += 1
            continue
        if not current_state:
            errors.append(f"Missing current_state for vector: {description[:30]}...")
            skipped_count += 1
            continue

        # Validate category enum
        valid_categories = ["trust", "risk_mitigation", "stakeholder", "value", "momentum"]
        if category not in valid_categories:
            errors.append(f"Invalid category '{category}'. Must be one of: {valid_categories}")
            skipped_count += 1
            continue

        # Validate state enum
        valid_states = ["ok", "warn", "risk"]
        if current_state not in valid_states:
            errors.append(f"Invalid current_state '{current_state}'. Must be one of: {valid_states}")
            skipped_count += 1
            continue

        # Normalize goal_id first (needed for duplicate check)
        normalized_goal_id = normalize_uuid(goal_id)

        # Check for duplicates (goal_id + category pair must be unique)
        vector_pair = (normalized_goal_id, category)
        if vector_pair in existing_pairs:
            logger.info(
                "vector_skipped_duplicate",
                customer_id=normalized_customer_id,
                goal_id=normalized_goal_id,
                category=category,
            )
            skipped_count += 1
            continue

        try:
            await dc.execute_mutation(
                "CreateProgressVector",
                {
                    "workspaceId": normalized_workspace_id,
                    "customerId": normalized_customer_id,
                    "goalId": normalized_goal_id,
                    "category": category,
                    "description": description,
                    "currentState": current_state,
                    "progress": vector.get("progress"),
                    "targetProgress": vector.get("target_progress"),
                    "targetLabel": vector.get("target_label"),
                    "unlocks": vector.get("unlocks"),
                    "assessmentReason": vector.get("assessment_reason"),
                    "lastAssessedBy": "agent:handoff_auto",
                },
            )
            created_count += 1
            existing_pairs.add(vector_pair)
        except Exception as e:
            logger.warning(
                "vector_creation_failed",
                customer_id=normalized_customer_id,
                description=description[:50],
                error=str(e),
            )
            errors.append(f"Failed to create vector '{description[:30]}...': {str(e)}")
            skipped_count += 1

    logger.info(
        "progress_vectors_created",
        customer_id=normalized_customer_id,
        created_count=created_count,
        skipped_count=skipped_count,
    )

    result = {
        "status": "success" if created_count > 0 else "partial" if skipped_count > 0 else "error",
        "created_count": created_count,
        "skipped_count": skipped_count,
        "message": f"Created {created_count} progress vector(s)"
        + (f", skipped {skipped_count}" if skipped_count > 0 else ""),
    }

    if errors:
        result["errors"] = errors[:5]  # Limit error list to prevent token bloat

    return result


async def create_customer_strategy(
    workspace_id: str,
    customer_id: str,
    customer_name: str,
    body: str,
) -> dict[str, Any]:
    """
    Create or update living strategy document for a customer.

    The customer strategy explains "why we're doing what we're doing" - different
    from the handoff brief (which is a point-in-time snapshot). The strategy is
    a living document that evolves as the engagement progresses.

    Call this alongside create_handoff_brief to capture strategic context.

    The body should cover:
    - Why this customer matters to us
    - What they're trying to achieve (their goals)
    - Key risks and how we're mitigating them
    - Our approach to building trust
    - Critical success factors
    - How we'll know we're succeeding

    Args:
        workspace_id: The workspace UUID
        customer_id: The customer UUID
        customer_name: The customer's name (for logging)
        body: Markdown document explaining strategy, risks, priorities

    Returns:
        Created/updated strategy with ID
    """
    # Validate required parameters
    if not body or len(body.strip()) < 100:
        return {
            "status": "error",
            "error": "The customer strategy body is too short or empty.",
            "hint": "The body should be a complete markdown document explaining why you're doing what you're doing, risks, priorities, approach. Minimum 100 characters.",
        }

    normalized_workspace_id = normalize_uuid(workspace_id)
    normalized_customer_id = normalize_uuid(customer_id)

    dc = get_dataconnect_client()

    # Check for existing strategy
    try:
        existing = await dc.execute_query(
            "GetCustomerStrategy",
            {"customerId": normalized_customer_id},
        )
        existing_strategies = existing.get("customerStrategies", [])
    except Exception:
        existing_strategies = []

    try:
        # Find-then-update-or-create. CustomerStrategy has no unique key on `customer`, so a real
        # `_upsert` can't be expressed (the DataConnect build rejects a keyless upsert). We already
        # looked up existing_strategies above, so branch on it: update the existing row, or insert a
        # new one with a fresh id.
        if existing_strategies:
            strategy_id = existing_strategies[0]["id"]
            await dc.execute_mutation(
                "UpdateCustomerStrategy",
                {"id": strategy_id, "body": body, "lastUpdatedBy": "agent:handoff_auto"},
            )
        else:
            strategy_id = str(uuid.uuid4())
            await dc.execute_mutation(
                "CreateCustomerStrategyWithId",
                {
                    "id": strategy_id,
                    "workspaceId": normalized_workspace_id,
                    "customerId": normalized_customer_id,
                    "body": body,
                    "lastUpdatedBy": "agent:handoff_auto",
                },
            )

        if not strategy_id:
            logger.warning(
                "customer_strategy_created_but_id_not_found",
                workspace_id=normalized_workspace_id,
                customer_id=normalized_customer_id,
                customer_name=customer_name,
            )
            return {
                "status": "error",
                "error": "Strategy created but ID could not be retrieved",
                "message": "Strategy may have been created. Check database.",
            }

        # Determine if this was create or update
        was_update = len(existing_strategies) > 0

        logger.info(
            "customer_strategy_upserted",
            workspace_id=normalized_workspace_id,
            customer_id=normalized_customer_id,
            customer_name=customer_name,
            strategy_id=strategy_id,
            was_update=was_update,
        )

        return {
            "status": "updated" if was_update else "created",
            "strategy_id": strategy_id,
            "message": f"Customer strategy {'updated' if was_update else 'created'} for {customer_name}.",
            "note": "This is a living document - update it as strategy evolves." if not was_update else None,
        }

    except Exception as e:
        logger.error(
            "customer_strategy_creation_failed",
            workspace_id=normalized_workspace_id,
            customer_id=normalized_customer_id,
            error=str(e),
        )
        return {
            "status": "error",
            "error": str(e),
            "message": "Failed to create customer strategy. Continuing without it.",
        }


async def create_handoff_brief(
    workspace_id: str,
    customer_id: str,
    customer_name: str,
    body: str,
    day_total: int | None = None,
    reality_check_confidence: str | None = None,
    notion_deal_id: str | None = None,
) -> dict[str, Any]:
    """
    Create a Handoff Brief document summarizing the sales handoff.

    The body should be a complete markdown document containing:
    - Customer overview
    - Sales commitments
    - Technical context
    - Timeline
    - Risks and concerns

    Call this BEFORE asking questions to ensure the brief exists for review.

    Args:
        workspace_id: The workspace UUID
        customer_id: The customer UUID
        customer_name: The customer's name (for logging)
        body: Complete markdown document with all handoff details
        day_total: Total planned onboarding days
        reality_check_confidence: Your confidence level (high/medium/low)
        notion_deal_id: Original Notion page ID if from Notion

    Returns:
        Created brief with ID
    """
    # Validate required parameters - return helpful errors to guide the LLM
    if not body or len(body.strip()) < 100:
        return {
            "status": "error",
            "error": "The handoff brief body is too short or empty.",
            "hint": "The body should be a complete markdown document with customer overview, sales commitments, technical context, timeline, and risks. Call get_customer_info first to gather the raw data.",
        }

    normalized_workspace_id = normalize_uuid(workspace_id)
    normalized_customer_id = normalize_uuid(customer_id)

    dc = get_dataconnect_client()

    # Check for existing brief for this customer
    existing = await dc.execute_query(
        "GetLatestHandoffBriefForCustomer",
        {"customerId": normalized_customer_id},
    )
    existing_briefs = existing.get("handoffBriefs", [])

    if existing_briefs:
        # Update existing brief instead of creating a new one
        existing_brief = existing_briefs[0]
        brief_id = existing_brief["id"]

        logger.info(
            "existing_brief_found_updating",
            workspace_id=normalized_workspace_id,
            customer_id=normalized_customer_id,
            brief_id=brief_id,
        )

        # Update the existing brief with new body
        update_result = await update_handoff_brief(
            brief_id=brief_id,
            body=body,
            day_total=day_total,
            reality_check_confidence=reality_check_confidence,
        )

        if update_result.get("status") == "updated":
            return {
                "status": "updated",
                "brief_id": brief_id,
                "message": f"Handoff brief updated for {customer_name}.",
                "note": "Found existing brief and UPDATED it with your new content. No duplicate created.",
                "next_step": "Proceed to generate_onboarding_plan with this brief_id",
            }
        else:
            # Update failed, return the error but still provide the brief_id
            return {
                "status": "existing",
                "brief_id": brief_id,
                "message": f"Using existing brief for {customer_name} (update failed: {update_result.get('error')})",
                "note": "Could not update existing brief. Using it as-is.",
                "next_step": "Proceed to generate_onboarding_plan with this brief_id",
            }

    # No existing brief, create a new one
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
                "body": body,
                "dayCurrent": 0,
                "dayTotal": day_total,
                "realityCheckConfidence": reality_check_confidence,
                "status": "draft",
                "notionDealId": notion_deal_id,
                "notionDealUrl": f"https://notion.so/{notion_deal_id.replace('-', '')}"
                if notion_deal_id
                else None,
                "handbookVersionId": handbook_version_id,
                "model": get_model(ModelUseCase.HANDOFF_BRIEF),
                "promptVersion": "adk_v1",
            },
        )

        # Query back to get the ID
        result = await dc.execute_query(
            "GetLatestHandoffBriefForCustomer",
            {"customerId": normalized_customer_id},
        )

        briefs = result.get("handoffBriefs", [])
        brief_id = briefs[0]["id"] if briefs else None

        if not brief_id:
            logger.warning(
                "handoff_brief_created_but_id_not_found",
                workspace_id=normalized_workspace_id,
                customer_id=normalized_customer_id,
                customer_name=customer_name,
            )
            return {
                "status": "error",
                "error": "Brief created but ID could not be retrieved",
                "message": "Brief may have been created. Check database.",
            }

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
            "message": f"Handoff brief created for {customer_name}.",
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


async def update_handoff_brief(
    brief_id: str,
    body: str | None = None,
    day_current: int | None = None,
    day_total: int | None = None,
    reality_check_confidence: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """
    Update an existing Handoff Brief with new information.

    Call this after receiving answers from humans to update the brief
    with clarified information.

    Args:
        brief_id: The brief's UUID
        body: Updated markdown body
        day_current: Updated current day
        day_total: Updated total days
        reality_check_confidence: Updated confidence level
        status: New status (draft, confirmed, needs_correction)

    Returns:
        Update confirmation
    """
    dc = get_dataconnect_client()

    try:
        # Build update fields
        update_fields = {"id": brief_id}
        if body is not None:
            update_fields["body"] = body
        if day_current is not None:
            update_fields["dayCurrent"] = day_current
        if day_total is not None:
            update_fields["dayTotal"] = day_total
        if reality_check_confidence is not None:
            update_fields["realityCheckConfidence"] = reality_check_confidence
        if status is not None:
            update_fields["status"] = status

        await dc.execute_mutation("UpdateHandoffBrief", update_fields)

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


async def generate_onboarding_plan(
    workspace_id: str,
    customer_id: str,
    customer_name: str,
    playbook_json: str,
    milestones_json: str,
    brief_id: str | None = None,
    context: str | None = None,
) -> dict[str, Any]:
    """
    Generate an AI-powered onboarding plan for a customer.

    Args:
        workspace_id: The workspace UUID
        customer_id: The customer UUID
        customer_name: The customer's name
        playbook_json: JSON string of playbook object from get_playbook_for_workspace
        milestones_json: JSON string of milestone templates from playbook. Each milestone should include:
            - title: The milestone name
            - owner_side: "us" or "them"
            - target_days: Days from start
            - description: Optional details
            - goal_id: UUID of the goal this milestone serves (REQUIRED)
            - goal_rationale: Why this milestone helps achieve the goal (REQUIRED)
        brief_id: The handoff brief UUID (from create_handoff_brief response)
        context: Optional additional context from memory/planning

    Returns:
        Generated plan with ID and milestones
    """
    # Validate required parameters - return helpful errors to guide the LLM
    if not playbook_json or playbook_json in ("None", "null", "", "{}"):
        return {
            "status": "error",
            "error": "Missing playbook_json. You must call get_playbook_for_workspace first.",
            "hint": "Call get_playbook_for_workspace to get the playbook, then pass it as playbook_json.",
        }

    if not milestones_json or milestones_json in ("None", "null", "", "[]"):
        return {
            "status": "error",
            "error": "Missing milestones_json. The playbook from get_playbook_for_workspace includes milestones.",
            "hint": "Use the 'milestones' array from the playbook returned by get_playbook_for_workspace.",
        }

    normalized_workspace_id = normalize_uuid(workspace_id)
    normalized_customer_id = normalize_uuid(customer_id)

    # Parse JSON parameters
    try:
        playbook = json.loads(playbook_json) if playbook_json else {}
        milestones = json.loads(milestones_json) if milestones_json else []
    except json.JSONDecodeError as e:
        logger.error("generate_plan_json_parse_error", error=str(e))
        return {
            "status": "error",
            "error": f"Invalid JSON: {e}",
            "hint": "Ensure playbook_json and milestones_json are valid JSON strings.",
        }

    dc = get_dataconnect_client()

    # Check for existing pending plan for this customer
    existing = await dc.execute_query(
        "GetExistingPendingPlan",
        {"customerId": normalized_customer_id},
    )
    existing_plans = existing.get("aiPlans", [])

    if existing_plans:
        # Use existing plan instead of creating a new one
        existing_plan = existing_plans[0]
        plan_id = existing_plan["id"]

        logger.info(
            "existing_plan_found",
            workspace_id=normalized_workspace_id,
            customer_id=normalized_customer_id,
            plan_id=plan_id,
            message="Using existing pending plan instead of creating duplicate",
        )

        # Store plan_id in context for the runner to retrieve
        set_plan_id(plan_id)

        return {
            "status": "existing",
            "plan_id": plan_id,
            "customer_name": customer_name,
            "milestone_count": existing_plan.get("milestoneCount", 0),
            "playbook_name": playbook.get("name"),
            "playbook_archetype": playbook.get("archetype"),
            "note": "A pending plan already exists for this customer. Do NOT create a new one.",
            "action_required": (
                "If you have NEW information from HITL answers that changes the milestones, "
                "call update_plan(plan_id, milestones_json, workspace_id) to modify the existing plan. "
                "If no changes needed, proceed to surface_need_for_review."
            ),
            "next_step": "Call surface_need_for_review with plan_id, milestone_count, and playbook_name from this response",
        }

    # Normalize brief_id if provided
    normalized_brief_id = normalize_uuid(brief_id) if brief_id else None

    try:
        # Create the AI plan
        plan_id = await _create_ai_plan(
            dc=dc,
            workspace_id=normalized_workspace_id,
            customer_id=normalized_customer_id,
            customer_name=customer_name,
            playbook=playbook,
            milestones=milestones,
            brief_id=normalized_brief_id,
            context=context,
        )

        logger.info(
            "onboarding_plan_generated",
            workspace_id=normalized_workspace_id,
            customer_id=normalized_customer_id,
            plan_id=plan_id,
            milestone_count=len(milestones),
        )

        # Store plan_id in context for the runner to retrieve
        set_plan_id(plan_id)

        return {
            "status": "generated",
            "plan_id": plan_id,  # Use this for surface_need_for_review
            "customer_name": customer_name,
            "milestone_count": len(milestones),
            "playbook_name": playbook.get("name"),
            "playbook_archetype": playbook.get("archetype"),
            "next_step": "Call surface_need_for_review with plan_id, milestone_count, and playbook_name from this response",
        }

    except Exception as e:
        logger.error(
            "onboarding_plan_generation_failed",
            workspace_id=normalized_workspace_id,
            customer_id=normalized_customer_id,
            error=str(e),
        )
        return {
            "status": "error",
            "error": str(e),
        }


async def _create_ai_plan(
    dc,
    workspace_id: str,
    customer_id: str,
    customer_name: str,
    playbook: dict[str, Any],
    milestones: list[dict[str, Any]],
    brief_id: str | None = None,
    context: str | None = None,
) -> str:
    """Internal helper to create an AI plan with milestones."""
    # Calculate total duration from milestones
    total_days = sum(m.get("target_days", 7) for m in milestones)

    # Create the AI plan record
    headline = f"Onboarding Plan for {customer_name}"
    duration_label = f"{total_days} days"

    # Prepare milestones JSON for storage on AiPlan record
    # This is displayed in the UI before plan approval
    milestones_for_display = [
        {
            "title": m.get("title", "Untitled milestone"),
            "owner_side": m.get("owner_side", "us"),
            "target_days": m.get("target_days", 7),
            "description": m.get("description"),
            "goal_id": m.get("goal_id"),
            "goal_rationale": m.get("goal_rationale"),
        }
        for m in milestones
    ]

    mutation_params = {
        "workspaceId": workspace_id,
        "customerId": customer_id,
        "headline": headline,
        "durationLabel": duration_label,
        "archetypeName": playbook.get("archetype"),
        "model": get_model(ModelUseCase.PLAN_GENERATION),
        "promptVersion": "adk_v1",
        "milestoneCount": len(milestones),
        "milestones": json.dumps(milestones_for_display),  # Store as JSON for UI display
    }

    # Link to brief if provided
    if brief_id:
        mutation_params["briefId"] = brief_id

    result = await dc.execute_mutation("CreateAiPlan", mutation_params)

    # Get the generated plan ID
    plan_id = result.get("aiPlan_insert", {}).get("id")
    if not plan_id:
        raise RuntimeError("Failed to create AI plan - no ID returned")

    return plan_id


async def surface_need_for_review(
    workspace_id: str,
    customer_id: str,
    customer_name: str,
    plan_id: str,
    milestone_count: int,
    playbook_name: str,
    quality_assessment_json: str | None = None,
) -> dict[str, Any]:
    """
    Surface a need in the Today queue for CSM to review the generated onboarding plan.

    This is the FINAL step after generating a plan. Creates a need of type
    'plan_approval_required' which appears in the Today queue.

    Args:
        workspace_id: The workspace UUID
        customer_id: The customer UUID
        customer_name: The customer's name
        plan_id: The generated plan's UUID (from generate_onboarding_plan response)
        milestone_count: Number of milestones in the plan
        playbook_name: Name of the playbook used
        quality_assessment_json: Optional JSON string of self-evaluation results (advisory only)

    Returns:
        Created need with ID
    """
    # Validate required parameters - return helpful errors to guide the LLM
    if not plan_id or plan_id in ("None", "null", ""):
        return {
            "status": "error",
            "error": "Missing plan_id. You must call generate_onboarding_plan first and use the 'plan_id' from its response.",
            "hint": "Call generate_onboarding_plan, then pass its returned plan_id to this function.",
        }

    if not playbook_name or playbook_name in ("None", "null", ""):
        return {
            "status": "error",
            "error": "Missing playbook_name. Use the 'playbook_name' from generate_onboarding_plan response.",
            "hint": "The playbook_name should come from generate_onboarding_plan's response.",
        }

    if not milestone_count or milestone_count < 1:
        return {
            "status": "error",
            "error": "Invalid milestone_count. Use the 'milestone_count' from generate_onboarding_plan response.",
            "hint": "The milestone_count should come from generate_onboarding_plan's response.",
        }

    logger.info(
        "surface_need_for_review_called",
        workspace_id=workspace_id,
        customer_id=customer_id,
        customer_name=customer_name,
        plan_id=plan_id,
        milestone_count=milestone_count,
        playbook_name=playbook_name,
    )

    normalized_workspace_id = normalize_uuid(workspace_id)
    normalized_customer_id = normalize_uuid(customer_id)
    normalized_plan_id = normalize_uuid(plan_id)

    # IMPORTANT: Set plan_id in context for completion tracking
    # This is needed because the agent may skip generate_onboarding_plan on resume
    # if a plan already exists, so we set it here as a backup
    set_plan_id(normalized_plan_id)

    # Parse optional quality assessment
    quality_assessment = None
    if quality_assessment_json:
        try:
            quality_assessment = json.loads(quality_assessment_json)
        except json.JSONDecodeError:
            pass  # Ignore invalid JSON for optional field

    # Build headline
    headline = f"Review onboarding plan for {customer_name}"

    # Build lede with quality notes if available
    lede = f"{milestone_count} milestones based on {playbook_name}"
    if quality_assessment:
        score = quality_assessment.get("quality_score", 0)
        if score < 0.5:
            lede += " [Low confidence - review carefully]"
        elif score < 0.7:
            lede += " [Medium confidence]"

    # Build reasoning (include plan_id for traceability)
    reasoning = f"Generated plan ({plan_id}) using {playbook_name} playbook."
    if quality_assessment:
        issues = quality_assessment.get("issues", [])
        if issues:
            reasoning += f" Advisory notes: {'; '.join(issues[:3])}"

    dc = get_dataconnect_client()

    try:
        # Check for existing unresolved plan_approval_required need for this customer
        existing = await dc.execute_query(
            "GetExistingNeedByType",
            {
                "customerId": normalized_customer_id,
                "needType": NeedType.PLAN_APPROVAL_REQUIRED.value,
            },
        )
        existing_needs = existing.get("needs", [])

        if existing_needs:
            # Use existing need instead of creating a new one
            existing_need = existing_needs[0]
            need_id = existing_need.get("id")

            logger.info(
                "existing_need_found",
                workspace_id=normalized_workspace_id,
                customer_id=normalized_customer_id,
                need_id=need_id,
                plan_id=plan_id,
                message="Using existing plan_approval_required need instead of creating duplicate",
            )

            # Store need_id in context for the runner to retrieve
            set_need_id(need_id)

            return {
                "id": need_id,
                "status": "surfaced",
                "plan_id": plan_id,
                "message": f"Plan surfaced for {customer_name}. CSM will review in Today queue.",
                "note": "Used existing need",
            }

        # No existing need, create a new one
        need = await insert_need(
            workspace_id=normalized_workspace_id,
            customer_id=normalized_customer_id,
            need_type=NeedType.PLAN_APPROVAL_REQUIRED.value,
            headline=headline,
            lede=lede,
            agent_reasoning=reasoning,
            priority_rank=3,  # High priority
        )

        need_id = need.get("id")

        logger.info(
            "need_surfaced_for_review",
            workspace_id=normalized_workspace_id,
            customer_id=normalized_customer_id,
            need_id=need_id,
            plan_id=plan_id,
        )

        # Store need_id in context for the runner to retrieve
        set_need_id(need_id)

        return {
            "id": need_id,
            "status": "surfaced",
            "plan_id": plan_id,
            "message": f"Plan surfaced for {customer_name}. CSM will review in Today queue.",
        }

    except Exception as e:
        logger.error(
            "need_surface_failed",
            workspace_id=normalized_workspace_id,
            customer_id=normalized_customer_id,
            plan_id=plan_id,
            error=str(e),
        )
        return {
            "status": "error",
            "error": str(e),
            "plan_id": plan_id,
        }


# =============================================================================
# PLAN UPDATE
# =============================================================================

async def update_plan(
    plan_id: str,
    milestones_json: str,
    workspace_id: str,
) -> dict[str, Any]:
    """
    Update an existing onboarding plan with new milestones.

    Use this when:
    - HITL answers require adjusting the plan milestones
    - Timeline information changes the plan structure
    - Customer feedback requires plan modifications

    Args:
        plan_id: The plan UUID to update
        milestones_json: JSON string of updated milestones array. Each milestone should have:
            - title: The milestone name
            - owner_side: "us" or "them" (who owns this milestone)
            - target_days: Days from start to complete
            - description: Optional details
        workspace_id: The workspace UUID

    Returns:
        Update confirmation with milestone count
    """
    normalized_plan_id = normalize_uuid(plan_id)
    normalized_workspace_id = normalize_uuid(workspace_id)

    # Parse milestones JSON
    try:
        milestones = json.loads(milestones_json) if milestones_json else []
    except json.JSONDecodeError as e:
        logger.error("update_plan_milestones_json_parse_error", error=str(e))
        return {"status": "error", "error": f"Invalid milestones JSON: {e}"}

    if not milestones:
        return {
            "status": "error",
            "error": "Milestones array is empty",
            "hint": "Provide at least one milestone with title, owner_side, and target_days",
        }

    dc = get_dataconnect_client()

    try:
        # Validate plan exists
        existing = await dc.execute_query("GetAiPlan", {"id": normalized_plan_id})
        plan = existing.get("aiPlan")
        if not plan:
            return {
                "status": "error",
                "error": f"Plan {normalized_plan_id} not found",
            }

        # Format milestones for storage
        # Preserve goal linkage (goal_id / goal_rationale) — without this, editing a
        # plan silently strips the goal-centric linkage that the architecture depends on.
        milestones_for_storage = [
            {
                "title": m.get("title", "Untitled milestone"),
                "owner_side": m.get("owner_side", "us"),
                "target_days": m.get("target_days", 7),
                "description": m.get("description"),
                "goal_id": m.get("goal_id"),
                "goal_rationale": m.get("goal_rationale"),
            }
            for m in milestones
        ]

        # Calculate duration
        total_days = sum(m.get("target_days", 7) for m in milestones)
        duration_label = f"{total_days} days"

        # Update the plan
        await dc.execute_mutation(
            "UpdatePlanMilestones",
            {
                "id": normalized_plan_id,
                "milestones": json.dumps(milestones_for_storage),
                "milestoneCount": len(milestones),
                "durationLabel": duration_label,
            },
        )

        logger.info(
            "plan_updated",
            plan_id=normalized_plan_id,
            workspace_id=normalized_workspace_id,
            milestone_count=len(milestones),
            duration_label=duration_label,
        )

        return {
            "status": "updated",
            "plan_id": normalized_plan_id,
            "milestone_count": len(milestones),
            "duration_label": duration_label,
            "message": f"Plan updated with {len(milestones)} milestones ({duration_label})",
        }

    except Exception as e:
        logger.error(
            "plan_update_failed",
            plan_id=normalized_plan_id,
            error=str(e),
        )
        return {
            "status": "error",
            "error": str(e),
            "plan_id": normalized_plan_id,
        }


# =============================================================================
# MEETING BRIEFS
# =============================================================================

async def create_meeting_brief(
    workspace_id: str,
    meeting_id: str,
    customer_name: str,
    progress_narrative: str,
    talking_points_json: str,
    progress_facts_json: str | None = None,
    friction: str | None = None,
    value_delivered: str | None = None,
    risk_to_renewal: str | None = None,
    expansion_signals: str | None = None,
    pricing_context: str | None = None,
    followup_email_json: str | None = None,
) -> dict[str, Any]:
    """
    Create a meeting brief for meeting preparation.

    A meeting brief helps CSMs prepare for customer calls by providing:
    - Progress narrative (what's happened since last touchpoint)
    - Key talking points for the meeting
    - Risks and opportunities to address

    Call this when preparing for an upcoming meeting. Gather context first using:
    - get_customer_info for customer data
    - recall_memory for past interactions

    Args:
        workspace_id: The workspace UUID
        meeting_id: The meeting UUID this brief is for
        customer_name: The customer's name (for logging)
        progress_narrative: Prose summary of progress since last touchpoint
        talking_points_json: JSON array of strings - key points to discuss
        progress_facts_json: Optional JSON array of factual bullet points
        friction: Optional description of current friction/blockers
        value_delivered: Optional summary of value delivered so far
        risk_to_renewal: Optional assessment of renewal risk
        expansion_signals: Optional expansion opportunity signals
        pricing_context: Optional pricing/contract context
        followup_email_json: Optional JSON object with suggested followup email

    Returns:
        Created meeting brief with ID
    """
    normalized_workspace_id = normalize_uuid(workspace_id)
    normalized_meeting_id = normalize_uuid(meeting_id)

    # Validate required fields
    if not progress_narrative or len(progress_narrative.strip()) < 50:
        return {
            "status": "error",
            "error": "Progress narrative is too short",
            "hint": "Provide a meaningful summary of recent progress (at least 50 characters)",
        }

    # Parse JSON fields
    try:
        talking_points = json.loads(talking_points_json) if talking_points_json else []
        if not talking_points:
            return {
                "status": "error",
                "error": "Talking points are required",
                "hint": "Provide at least one talking point for the meeting",
            }
    except json.JSONDecodeError as e:
        return {"status": "error", "error": f"Invalid talking_points JSON: {e}"}

    progress_facts = None
    if progress_facts_json:
        try:
            progress_facts = json.loads(progress_facts_json)
        except json.JSONDecodeError:
            pass  # Optional field, ignore parse errors

    followup_email = None
    if followup_email_json:
        try:
            followup_email = json.loads(followup_email_json)
        except json.JSONDecodeError:
            pass  # Optional field, ignore parse errors

    dc = get_dataconnect_client()

    try:
        # Check meeting exists
        meeting_result = await dc.execute_query(
            "GetMeeting",
            {"id": normalized_meeting_id},
        )
        meeting = meeting_result.get("meeting")
        if not meeting:
            return {
                "status": "error",
                "error": f"Meeting {normalized_meeting_id} not found",
            }

        # Check for existing brief for this meeting
        existing_result = await dc.execute_query(
            "GetMeetingBriefByMeeting",
            {"meetingId": normalized_meeting_id},
        )
        existing_briefs = existing_result.get("meetingBriefs", [])

        if existing_briefs:
            # Update existing brief instead of creating duplicate
            existing_brief = existing_briefs[0]
            brief_id = existing_brief["id"]

            await dc.execute_mutation(
                "UpdateMeetingBrief",
                {
                    "id": brief_id,
                    "progressNarrative": progress_narrative,
                    "progressFacts": json.dumps(progress_facts) if progress_facts else None,
                    "friction": friction,
                    "talkingPoints": json.dumps(talking_points),
                    "valueDelivered": value_delivered,
                    "riskToRenewal": risk_to_renewal,
                    "expansionSignals": expansion_signals,
                    "pricingContext": pricing_context,
                    "followupEmail": json.dumps(followup_email) if followup_email else None,
                },
            )

            logger.info(
                "meeting_brief_updated",
                brief_id=brief_id,
                meeting_id=normalized_meeting_id,
                workspace_id=normalized_workspace_id,
            )

            return {
                "status": "updated",
                "brief_id": brief_id,
                "meeting_id": normalized_meeting_id,
                "message": f"Meeting brief updated for {customer_name}",
            }

        # Create new brief
        # Generate inputs hash for deduplication
        import hashlib
        inputs_hash = hashlib.sha256(
            f"{normalized_meeting_id}:{progress_narrative}".encode()
        ).hexdigest()[:16]

        result = await dc.execute_mutation(
            "CreateMeetingBrief",
            {
                "workspaceId": normalized_workspace_id,
                "meetingId": normalized_meeting_id,
                "progressNarrative": progress_narrative,
                "progressFacts": json.dumps(progress_facts) if progress_facts else None,
                "friction": friction,
                "talkingPoints": json.dumps(talking_points),
                "valueDelivered": value_delivered,
                "riskToRenewal": risk_to_renewal,
                "expansionSignals": expansion_signals,
                "pricingContext": pricing_context,
                "followupEmail": json.dumps(followup_email) if followup_email else None,
                "model": "gemini-2.0-flash",
                "promptVersion": "adk_v1",
                "inputsHash": inputs_hash,
                "handbookVersionId": "00000000-0000-0000-0000-000000000000",  # Placeholder
            },
        )

        brief_id = (result.get("meetingBrief_insert") or {}).get("id")

        logger.info(
            "meeting_brief_created",
            brief_id=brief_id,
            meeting_id=normalized_meeting_id,
            workspace_id=normalized_workspace_id,
            talking_points_count=len(talking_points),
        )

        return {
            "status": "created",
            "brief_id": brief_id,
            "meeting_id": normalized_meeting_id,
            "talking_points_count": len(talking_points),
            "message": f"Meeting brief created for {customer_name}",
        }

    except Exception as e:
        logger.error(
            "meeting_brief_creation_failed",
            meeting_id=normalized_meeting_id,
            workspace_id=normalized_workspace_id,
            error=str(e),
        )
        return {
            "status": "error",
            "error": str(e),
        }

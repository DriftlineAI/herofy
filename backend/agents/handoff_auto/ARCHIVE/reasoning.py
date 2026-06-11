"""
Agent Reasoning & Planning
Task decomposition, self-evaluation, and self-healing for the autonomous agent
"""

from typing import Any
from google import genai
from google.genai import types

from config import settings
from core.logging import get_logger
from core.model_config import get_model, ModelUseCase

logger = get_logger("AgentReasoning")


async def create_execution_plan(
    goal: str,
    context: dict[str, Any],
    memory_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Break down a goal into an explicit execution plan.

    The agent creates a task list before taking action, making its
    reasoning visible and auditable.

    Args:
        goal: What the agent needs to accomplish
        context: Current context (customer_id, workspace_id, etc.)
        memory_context: Optional context from memory (past plans, patterns)

    Returns:
        Execution plan with tasks, reasoning, and success criteria
    """
    client = genai.Client(api_key=settings.gemini_api_key)

    memory_summary = ""
    if memory_context:
        if memory_context.get("past_plans"):
            plans = memory_context["past_plans"][:3]
            memory_summary += f"\n\nPast plans for reference ({len(plans)} shown):\n"
            for p in plans:
                memory_summary += f"- {p.get('headline')}: {p.get('status')}, edited={p.get('was_edited')}\n"

        if memory_context.get("success_patterns", {}).get("insights"):
            memory_summary += f"\n\nSuccess patterns:\n"
            for insight in memory_context["success_patterns"]["insights"][:3]:
                memory_summary += f"- {insight}\n"

        if memory_context.get("similar_customers"):
            memory_summary += f"\n\nSimilar customers: {len(memory_context['similar_customers'])} found\n"

    prompt = f"""You are creating YOUR internal execution checklist for completing an autonomous agent task.

IMPORTANT: This checklist is YOUR internal task list - it describes which TOOLS you (the agent) will call.
This is NOT the customer's onboarding plan. The customer's onboarding plan is created later using `generate_onboarding_plan`.

YOUR GOAL: {goal}

CONTEXT:
- Workspace ID: {context.get('workspace_id')}
- Customer ID: {context.get('customer_id')}
- Customer Name: {context.get('customer_name', 'Unknown')}
- Customer Tier: {context.get('customer_tier', 'Unknown')}
- ARR: ${((context.get('arr_cents') or 0) / 100):,.0f}
{memory_summary}

Create YOUR execution checklist. Each task should be a TOOL CALL you will make:
1. Which tool to call
2. Why you need this information
3. What could go wrong
4. Fallback if it fails

Available tools you should reference:
- get_customer_info: Fetch customer data, raw_notes, linked_pages
- get_workspace_settings: Check autonomy mode, value_proposition
- get_customer_goals: Check if goals exist
- get_playbook_for_workspace: Get the onboarding template
- get_handbook_guide: Get guidance on approach
- create_handoff_brief: Document sales commitments and context
- pause_for_human_input: Ask clarifying questions
- generate_onboarding_plan: Create the CUSTOMER'S onboarding milestones
- surface_need_for_review: Surface the plan for human approval

Respond in JSON format:
{{
    "checklist_summary": "Brief description of YOUR execution approach",
    "tasks": [
        {{
            "id": 1,
            "action": "What YOU will do (which tool to call)",
            "reason": "Why you need this",
            "tool": "tool_name",
            "risks": ["What could go wrong"],
            "fallback": "What to do if this fails"
        }}
    ],
    "success_criteria": ["How to know YOUR execution succeeded"],
    "estimated_confidence": 0.0-1.0
}}"""

    try:
        response = await client.aio.models.generate_content(
            model=get_model(ModelUseCase.PLAN_GENERATION),
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )

        import json
        plan = json.loads(response.text)

        # Normalize the response (support both old and new field names)
        if "plan_summary" in plan and "checklist_summary" not in plan:
            plan["checklist_summary"] = plan.pop("plan_summary")

        logger.info(
            "execution_checklist_created",
            task_count=len(plan.get("tasks", [])),
            confidence=plan.get("estimated_confidence"),
        )

        return plan

    except Exception as e:
        logger.error("execution_checklist_failed", error=str(e))
        # Return a basic fallback checklist
        return {
            "checklist_summary": "Basic execution checklist (planning failed)",
            "tasks": [
                {"id": 1, "action": "Fetch customer data", "tool": "get_customer_info"},
                {"id": 2, "action": "Check workspace settings", "tool": "get_workspace_settings"},
                {"id": 3, "action": "Get playbook template", "tool": "get_playbook_for_workspace"},
                {"id": 4, "action": "Create handoff brief", "tool": "create_handoff_brief"},
                {"id": 5, "action": "Generate customer's onboarding plan", "tool": "generate_onboarding_plan"},
                {"id": 6, "action": "Surface for human review", "tool": "surface_need_for_review"},
            ],
            "success_criteria": ["Handoff brief created", "Customer onboarding plan created", "Need surfaced for review"],
            "estimated_confidence": 0.5,
            "error": str(e),
        }


async def evaluate_plan_quality(
    plan: dict[str, Any],
    customer_context: dict[str, Any],
    playbook: dict[str, Any],
    memory_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Self-evaluate the quality of a generated plan before surfacing.

    The agent critically reviews its own output and suggests improvements.

    Args:
        plan: The generated onboarding plan
        customer_context: Customer info (tier, ARR, etc.)
        playbook: The playbook used
        memory_context: Past patterns for comparison

    Returns:
        Quality assessment with score, issues, and suggestions
    """
    client = genai.Client(api_key=settings.gemini_api_key)

    # Build comparison context from memory
    comparison = ""
    if memory_context:
        patterns = memory_context.get("success_patterns", {})
        if patterns.get("tier_patterns"):
            tier_match = next(
                (t for t in patterns["tier_patterns"] if t.get("tier") == customer_context.get("tier")),
                None,
            )
            if tier_match:
                comparison += f"\n\nTypical for {tier_match.get('tier')} tier:"
                comparison += f"\n- Average milestones: {tier_match.get('avg_milestones')}"
                comparison += f"\n- Approval rate: {tier_match.get('approval_rate'):.0f}%"

    prompt = f"""You are evaluating the quality of an AI-generated onboarding plan.

CUSTOMER CONTEXT:
- Name: {customer_context.get('name', 'Unknown')}
- Tier: {customer_context.get('tier', 'Unknown')}
- ARR: ${((customer_context.get('arr_cents') or 0) / 100):,.0f}

PLAYBOOK USED: {playbook.get('name', 'Unknown')} ({playbook.get('archetype', 'Standard')})

GENERATED PLAN:
- Headline: {plan.get('headline')}
- Milestones: {plan.get('milestone_count')}
- Duration: {plan.get('duration_label')}
{comparison}

Evaluate this plan critically:

1. Is the timeline realistic for this customer tier/ARR?
2. Are the milestones appropriate?
3. Are there any red flags?
4. What would a CSM likely want to change?

Respond in JSON:
{{
    "quality_score": 0.0-1.0,
    "confidence": 0.0-1.0,
    "issues": ["List of potential issues"],
    "suggestions": ["Specific improvements"],
    "would_approve_immediately": true/false,
    "reasoning": "Why you gave this score"
}}"""

    try:
        response = await client.aio.models.generate_content(
            model=get_model(ModelUseCase.PLAN_GENERATION),
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )

        import json
        evaluation = json.loads(response.text)

        logger.info(
            "plan_evaluated",
            quality_score=evaluation.get("quality_score"),
            would_approve=evaluation.get("would_approve_immediately"),
            issue_count=len(evaluation.get("issues", [])),
        )

        return evaluation

    except Exception as e:
        logger.error("plan_evaluation_failed", error=str(e))
        return {
            "quality_score": 0.7,
            "confidence": 0.5,
            "issues": ["Evaluation failed - proceeding with caution"],
            "suggestions": [],
            "would_approve_immediately": False,
            "reasoning": f"Evaluation error: {str(e)}",
        }


async def decide_recovery_action(
    failure: str,
    context: dict[str, Any],
    attempted_actions: list[str],
) -> dict[str, Any]:
    """
    Self-healing: Decide how to recover from a failure.

    The agent analyzes what went wrong and proposes an alternative approach.

    Args:
        failure: Description of what failed
        context: Current context
        attempted_actions: What has been tried so far

    Returns:
        Recovery decision with action and reasoning
    """
    client = genai.Client(api_key=settings.gemini_api_key)

    prompt = f"""You are an autonomous agent that encountered a failure and needs to decide how to recover.

FAILURE: {failure}

CONTEXT:
- Workspace: {context.get('workspace_id')}
- Customer: {context.get('customer_id')}

ATTEMPTED ACTIONS:
{chr(10).join(f'- {a}' for a in attempted_actions)}

Decide on a recovery action:

1. Can you retry with different parameters?
2. Can you skip this step and continue?
3. Should you ask for human help?
4. Should you fail gracefully?

Respond in JSON:
{{
    "action": "retry|skip|ask_human|fail",
    "reasoning": "Why this is the best recovery",
    "retry_with": {{"param": "value"}} or null,
    "skip_to": "next_step_name" or null,
    "human_question": "Question to ask" or null,
    "graceful_failure_message": "Message for user" or null
}}"""

    try:
        response = await client.aio.models.generate_content(
            model=get_model(ModelUseCase.PLAN_GENERATION),
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )

        import json
        decision = json.loads(response.text)

        logger.info(
            "recovery_decided",
            action=decision.get("action"),
            reasoning=decision.get("reasoning"),
        )

        return decision

    except Exception as e:
        logger.error("recovery_decision_failed", error=str(e))
        return {
            "action": "fail",
            "reasoning": f"Could not determine recovery: {str(e)}",
            "graceful_failure_message": "The agent encountered an error and could not recover automatically.",
        }


async def reflect_on_execution(
    execution_log: list[dict[str, Any]],
    outcome: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """
    Post-execution reflection for learning.

    The agent reviews what happened and extracts learnings for future runs.

    Args:
        execution_log: Log of actions taken
        outcome: Final outcome (success/failure)
        context: Execution context

    Returns:
        Reflection with learnings and recommendations
    """
    client = genai.Client(api_key=settings.gemini_api_key)

    log_summary = "\n".join([
        f"- {entry.get('action')}: {entry.get('result', 'unknown')}"
        for entry in execution_log[:10]
    ])

    prompt = f"""Review this agent execution and extract learnings.

OUTCOME: {outcome}

EXECUTION LOG:
{log_summary}

CONTEXT:
- Customer tier: {context.get('customer_tier', 'Unknown')}
- ARR: ${((context.get('arr_cents') or 0) / 100):,.0f}

Reflect on:
1. What went well?
2. What could be improved?
3. Any patterns to remember for similar customers?

Respond in JSON:
{{
    "went_well": ["List of things that worked"],
    "improvements": ["What to do differently"],
    "patterns_learned": ["Patterns to apply to similar cases"],
    "confidence_for_next_run": 0.0-1.0
}}"""

    try:
        response = await client.aio.models.generate_content(
            model=get_model(ModelUseCase.PLAN_GENERATION),
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )

        import json
        reflection = json.loads(response.text)

        logger.info(
            "execution_reflected",
            outcome=outcome,
            learnings_count=len(reflection.get("patterns_learned", [])),
        )

        return reflection

    except Exception as e:
        logger.error("reflection_failed", error=str(e))
        return {
            "went_well": [],
            "improvements": [],
            "patterns_learned": [],
            "confidence_for_next_run": 0.5,
            "error": str(e),
        }

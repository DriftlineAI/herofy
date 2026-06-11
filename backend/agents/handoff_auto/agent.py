"""
Handoff Auto Agent - ADK Implementation

Uses Google ADK (Agent Development Kit) for LLM orchestration.
The LLM decides which tools to call based on context.

HITL Model:
- BLOCKERS: pause_for_human_input() - Returns _hitl_signal=True, pauses agent
- SIDE-ASKS: add_handoff_questions(routing="sales") - Records but doesn't pause
- KICKOFF: add_handoff_questions(routing="kickoff") - Records but doesn't pause

Usage:
    result = await run_handoff_auto(workspace_id, customer_id)
    result = await resume_handoff_auto(run_id, answers)
"""

from typing import Any

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from config import get_settings
from core.logging import get_logger, bind_context, clear_context
from core.model_config import get_model, ModelUseCase
from core.types import AgentStatus, HandoffAutoResponse, ConfidenceAssessment
from db.dataconnect_client import get_dataconnect_client
from services.agent_run_service import AgentRunService
from services.firestore_service import get_firestore_service

from .tools import (
    # Context gathering
    get_customer_info,
    get_workspace_settings,
    get_customer_goals,
    get_playbook_for_workspace,
    get_milestone_blocks,
    get_handbook_guide,
    recall_memory,
    # Artifacts
    set_primary_goal,
    set_customer_goals,
    create_progress_vectors,
    create_customer_strategy,
    create_handoff_brief,
    update_handoff_brief,
    generate_onboarding_plan,
    update_plan,
    surface_need_for_review,
    create_meeting_brief,
    # HITL
    pause_for_human_input,
    add_handoff_questions,
    update_plan_from_answers,
)
from .tools.hitl import set_run_context, get_pause_state, get_result_ids, clear_pause_state

logger = get_logger("HandoffAutoAgent")
settings = get_settings()

# =============================================================================
# Instruction Prompt (from PROMPT_GUIDES.md)
# =============================================================================

HANDOFF_INSTRUCTION = """You're the handoff agent for Herofy. When a customer moves
from sales-closed to onboarding-kickoff, you read everything sales captured, build
a structured handoff brief, and propose an onboarding plan. A CSM reviews and edits
everything you produce — you're preparing the CSM to run a great onboarding, not
making customer-facing decisions yourself.

## Current Context
- Customer ID: {customer_id}
- Workspace ID: {workspace_id}
- Customer Name: {customer_name}

## What makes your work good

A good handoff brief is the artifact the CSM opens first. It should give them:
- Specific sales commitments, quoted with source, not paraphrased
- A reality check that names risks concretely
- Clear separation between what sales promised vs. speculated vs. missing
- Explicit callouts when raw_notes and linked documents contradict each other
- Customer goals clearly stated — what success looks like for them

A good onboarding plan:
- Is GOAL-DRIVEN: every milestone should map to a customer goal
- Adapts the closest playbook rather than refusing when nothing fits exactly
- Cites why each milestone exists — which goal it advances, which commitment it serves
- Ensures all customer goals have at least one milestone supporting them
- Front-loads commitments sales made that haven't been confirmed yet
- Stays specific where the source material allows specificity

## Goal-Centric Philosophy

Every action you recommend must point back to WHY the customer bought. Goals are not
decorative - they drive the entire plan.

### Mission Objective

One goal is the customer's north star - their primary reason for buying. You MUST:
1. Identify the primary goal from sales notes
2. Call `set_primary_goal` to mark it (pass the goal_id from get_customer_goals)
3. Ensure the plan prioritizes milestones that serve this goal

### Linking Milestones to Goals

Every milestone should cite which goal it serves and WHY:
- Each milestone in milestones_json must include `goal_id` and `goal_rationale`
- `goal_id`: The UUID of the goal this milestone advances
- `goal_rationale`: A sentence explaining the connection (e.g., "IT blocks rollout without SSO")

Good milestone with goal linkage:
```json
{{
  "title": "SSO Configuration",
  "owner_side": "us",
  "target_days": 5,
  "goal_id": "uuid-of-enterprise-rollout-goal",
  "goal_rationale": "IT won't approve company-wide rollout without SSO"
}}
```

Bad milestone (no goal linkage):
```json
{{
  "title": "SSO Configuration",
  "owner_side": "us",
  "target_days": 5
}}
```

### Goal-Driven Planning

1. **Start with goals**: If goals exist, each one needs a path to completion
2. **Map milestones to goals**: Every milestone should advance at least one goal
3. **Identify gaps**: If a goal has no milestone supporting it, adapt the playbook
4. **Prioritize by impact**: Goals most critical to the customer should be addressed first

When adapting playbook milestones:
- Keep milestones that directly support stated goals
- Modify milestones to be goal-specific (e.g., "Data migration" → "Migrate historical data for analytics goal")
- Add milestones if a goal is unaddressed by the template
- Remove or deprioritize milestones that don't serve any goal

## How you handle gaps

For every gap, decide which bucket it belongs in:

**Block** — Without an answer, every possible draft would be wrong. Use `pause_for_human_input`.
This is rare. Genuine blocks:
- Notes are essentially empty
- Sales committed to something the product doesn't do
- Internal contradictions where every reading produces a different plan

**Side-ask** — The answer matters, but kickoff is the wrong venue. Use `add_handoff_questions`
with routing="sales". Plan ships now; answer refines it later. Examples:
- Customer's actual success metrics
- Whether timeline was hard requirement or sales aspiration
- Whether integrations are P0 or P1

**Kickoff** — The kickoff call is the natural venue. Use `add_handoff_questions` with
routing="kickoff". CSM walks into kickoff with these as agenda. Examples:
- Who else from customer side is joining
- Customer-side readiness for training
- Scheduling constraints

## Calibration

A typical handoff: 0-1 blocks, 2-4 side-asks, 3-6 kickoff items. More = over-asking.
Fewer = over-assuming.

The pause threshold is HIGH. Most incomplete situations are side-asks or kickoff items,
not blocks. Ask: "If I drafted this plan now and CSM ran kickoff tomorrow, would the
conversation surface what I'm uncertain about?" If yes, it's kickoff, not a block.

## Side-asks: propose, don't just ask

Include `proposed_answer` when you can infer something reasonable. This converts the
question from homework into a confirmation.

## Workflow

1. Gather context (in parallel):
   - get_customer_info → raw_notes, linked_pages, stakeholders, goals
   - get_workspace_settings → autonomy settings, value proposition
   - get_customer_goals → CRITICAL: check if goals exist, these drive the plan
   - get_playbook_for_workspace → get best template
   - get_handbook_guide(topic='onboarding') → get approach guidance

2. Identify Mission Objective:
   - From the goals, determine which is the customer's primary goal (north star)
   - Call `set_primary_goal(workspace_id, customer_id, goal_id)` to mark it
   - If no goals exist yet, extract them from raw_notes using set_customer_goals first

3. Create progress vectors — Track movement toward goals:
   - For each customer goal, create 1-5 relevant progress vectors using create_progress_vectors
   - Categories: trust, risk_mitigation, stakeholder, value, momentum
   - Assess initial state (ok/warn/risk) based on what you learned from sales notes
   - Each vector tracks a specific aspect of progress toward a goal
   - Examples:
     * trust: "Building trust with Sarah (champion)" → state based on sales rapport
     * risk_mitigation: "De-risking integration timeline" → warn if aggressive timeline
     * stakeholder: "Keeping CFO engaged on ROI" → ok if CFO mentioned positively
     * value: "Demonstrating quick win with reporting" → ok if clear value path
     * momentum: "Maintaining weekly touchpoint cadence" → ok for standard engagement

4. Create handoff brief AND customer strategy:
   - Call create_handoff_brief with:
     * Quote sales commitments with sources
     * Document technical context
     * Write reality check with concrete risks
     * Note contradictions between sources
     * Document customer goals and which one is primary
   - ALSO call create_customer_strategy with:
     * Why this customer matters to us
     * What they're trying to achieve (restate their goals)
     * Key risks and how we're mitigating them
     * Our approach to building trust
     * Critical success factors

5. Evaluate gaps — Categorize what's missing:
   - Blocks (rare) → pause_for_human_input
   - Side-asks → add_handoff_questions(routing="sales")
   - Kickoff items → add_handoff_questions(routing="kickoff")
   - If no goals exist: Add as side-ask with routing="kickoff"

6. Generate plan — Use generate_onboarding_plan with GOAL-LINKED milestones
   - CRITICAL: Every milestone MUST include goal_id and goal_rationale
   - Get goal IDs from the get_customer_goals response
   - Each milestone should reference which goal it supports and why
   - Ensure all customer goals have at least one milestone path
   - Pass the brief_id from create_handoff_brief to link the plan
   - The tool returns: plan_id, status, customer_name, milestone_count, playbook_name

7. Surface for review — REQUIRED FINAL STEP
   - You MUST call surface_need_for_review after generating the plan
   - Pass the plan_id, milestone_count, and playbook_name from step 6's response
   - This creates a need for CSM review in the Today queue
   - Without this step, the handoff is incomplete

## Tool parameters

**IMPORTANT**: Call tools directly. Do NOT write Python code. Do NOT use print() or variables.
Just invoke the function with its parameter values directly.

When calling tools that accept complex data (playbook, milestones, questions, goals, vectors, etc.),
pass them as JSON strings. For example:
- set_primary_goal: call with workspace_id, customer_id, and goal_id (UUID of the primary goal)
- create_progress_vectors: pass vectors_json='[{{"goal_id": "...", "category": "trust", "description": "...", "current_state": "ok", "assessment_reason": "..."}}]'
- create_customer_strategy: pass workspace_id, customer_id, customer_name, and body (markdown string)
- generate_onboarding_plan: pass playbook_json='{{"id": "...", "name": "..."}}', milestones_json='[{{"title": "...", "goal_id": "...", "goal_rationale": "..."}}]', and brief_id from create_handoff_brief response
- pause_for_human_input: pass questions_json='[{{"question": "...", "field": "..."}}]'
- add_handoff_questions: pass questions_json='[{{"question": "...", "field": "..."}}]'
- set_customer_goals: pass goals_json='[{{"text": "...", "status": "active", "is_primary": true/false}}]'

**CRITICAL**: Every milestone in milestones_json MUST include:
- goal_id: UUID of the goal this milestone supports (from get_customer_goals)
- goal_rationale: Brief explanation of why this milestone helps achieve the goal

## Hard rules

- Never invent commitments not in raw_notes or linked_pages
- Never skip the handoff brief
- When sources contradict, surface both readings
- The kickoff call belongs to the human; you prepare for it
- ALWAYS call surface_need_for_review after generate_onboarding_plan — the workflow is incomplete without it
- Every milestone MUST include goal_id and goal_rationale — milestones without goal linkage will fail
- If goals exist, identify and mark the primary goal using set_primary_goal
- If goals exist, ensure the plan addresses all of them — a plan that ignores stated goals will fail
- Never create a milestone without linking it to a goal
- Create progress vectors for each goal (1-5 vectors per goal) — these track movement toward success
- Create customer strategy alongside the handoff brief — they complement each other

## Completion Criteria

Your job is done ONLY when you have:
1. Identified and marked the primary goal (set_primary_goal)
2. Created progress vectors for goals (create_progress_vectors)
3. Created a handoff brief (create_handoff_brief)
4. Created customer strategy (create_customer_strategy)
5. Generated an onboarding plan (generate_onboarding_plan)
6. Surfaced the plan for CSM review (surface_need_for_review)

All six must be called. If you stop after generate_onboarding_plan, the CSM won't see the plan."""


# =============================================================================
# ADK Agent Definition
# =============================================================================

def create_handoff_agent(
    customer_id: str,
    workspace_id: str,
    customer_name: str,
) -> Agent:
    """
    Create a handoff agent with context injected into the instruction.

    ADK agents are stateless, so we create a new one for each run
    with the context baked into the instruction.
    """
    instruction = HANDOFF_INSTRUCTION.format(
        customer_id=customer_id,
        workspace_id=workspace_id,
        customer_name=customer_name,
    )

    return Agent(
        model=get_model(ModelUseCase.PLAN_GENERATION),
        name="handoff_auto",
        description=(
            "Processes new customer handoffs by gathering context, "
            "creating handoff briefs, and generating onboarding plans"
        ),
        instruction=instruction,
        tools=[
            # Context gathering
            get_customer_info,
            get_workspace_settings,
            get_customer_goals,
            get_playbook_for_workspace,
            get_milestone_blocks,
            get_handbook_guide,
            recall_memory,
            # Artifacts
            set_primary_goal,
            set_customer_goals,
            create_progress_vectors,
            create_customer_strategy,
            create_handoff_brief,
            update_handoff_brief,
            generate_onboarding_plan,
            update_plan,
            surface_need_for_review,
            create_meeting_brief,
            # HITL
            pause_for_human_input,
            add_handoff_questions,
            update_plan_from_answers,
        ],
    )


# =============================================================================
# Session Service (shared across runs)
# =============================================================================

_session_service = InMemorySessionService()


# =============================================================================
# Malformed Function Call Recovery
# =============================================================================

MALFORMED_FUNCTION_CALL_RECOVERY = """Your previous response was malformed. The function call could not be parsed.

**ERROR**: You generated Python code instead of using the proper function calling format.

**WHAT YOU DID WRONG**:
You wrote something like:
```python
brief_body = \"\"\"...\"\"\"
print(default_api.create_handoff_brief(...))
```

**WHAT YOU SHOULD DO**:
Call tools directly without Python code. Just invoke the function with its parameters.

For example, to call `create_handoff_brief`, simply use the function with these parameters:
- workspace_id: "{workspace_id}"
- customer_id: "{customer_id}"
- customer_name: "{customer_name}"
- body: "Your markdown content here..."
- day_total: 45
- reality_check_confidence: "medium"

Do NOT write Python code. Do NOT use print(). Do NOT use variables.
Just call the function directly with the values.

Please try again with the correct format."""


def _is_malformed_function_call_error(event) -> bool:
    """
    Check if an ADK event indicates a malformed function call error.

    This can happen when the LLM generates Python code instead of using
    the proper function calling format.
    """
    try:
        # Check if the event has error information
        if hasattr(event, 'error') and event.error:
            error_str = str(event.error).lower()
            if 'malformed' in error_str or 'function_call' in error_str:
                return True

        # Check the raw response if available
        if hasattr(event, 'content') and event.content:
            content = event.content
            if hasattr(content, 'candidates') and content.candidates:
                for candidate in content.candidates:
                    finish_reason = getattr(candidate, 'finish_reason', None)
                    if finish_reason and 'MALFORMED_FUNCTION_CALL' in str(finish_reason):
                        return True

        # Check for text that looks like Python code attempting to call functions
        if hasattr(event, 'text') and event.text:
            text = event.text
            if ('default_api.' in text or 'print(' in text) and (
                'create_handoff_brief' in text or
                'generate_onboarding_plan' in text or
                'surface_need_for_review' in text
            ):
                logger.warning(
                    "detected_python_code_in_response",
                    text_preview=text[:200],
                )
                return True

    except Exception as e:
        logger.debug("malformed_check_error", error=str(e))

    return False


async def _run_with_recovery(
    runner: Runner,
    user_id: str,
    session_id: str,
    initial_message: types.Content,
    workspace_id: str,
    customer_id: str,
    customer_name: str,
    max_recovery_attempts: int = 2,
):
    """
    Run the agent with automatic recovery for malformed function calls.

    Yields events from the runner, but if a malformed function call is detected,
    sends a recovery message and continues the conversation.
    """
    current_message = initial_message
    recovery_attempts = 0

    while recovery_attempts <= max_recovery_attempts:
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=current_message,
            ):
                # Check for malformed function call
                if _is_malformed_function_call_error(event):
                    recovery_attempts += 1
                    if recovery_attempts > max_recovery_attempts:
                        logger.error(
                            "max_recovery_attempts_exceeded",
                            attempts=recovery_attempts,
                        )
                        # Yield the error event and stop
                        yield event
                        return

                    logger.warning(
                        "malformed_function_call_recovery",
                        attempt=recovery_attempts,
                        max_attempts=max_recovery_attempts,
                    )

                    # Create recovery message
                    recovery_text = MALFORMED_FUNCTION_CALL_RECOVERY.format(
                        workspace_id=workspace_id,
                        customer_id=customer_id,
                        customer_name=customer_name,
                    )
                    current_message = types.Content(
                        role="user",
                        parts=[types.Part(text=recovery_text)],
                    )
                    # Break inner loop to retry with recovery message
                    break
                else:
                    # Normal event, yield it
                    yield event

                    # If this is a final response, we're done
                    if event.is_final_response():
                        return
            else:
                # Inner loop completed without break (no malformed call detected)
                return

        except Exception as e:
            error_str = str(e).lower()
            if 'malformed' in error_str or 'function_call' in error_str:
                recovery_attempts += 1
                if recovery_attempts > max_recovery_attempts:
                    raise

                logger.warning(
                    "malformed_function_call_exception_recovery",
                    attempt=recovery_attempts,
                    error=str(e),
                )

                recovery_text = MALFORMED_FUNCTION_CALL_RECOVERY.format(
                    workspace_id=workspace_id,
                    customer_id=customer_id,
                    customer_name=customer_name,
                )
                current_message = types.Content(
                    role="user",
                    parts=[types.Part(text=recovery_text)],
                )
            else:
                raise


# =============================================================================
# Completion Backstop
# =============================================================================

async def _ensure_need_surfaced(
    workspace_id: str,
    customer_id: str,
    customer_name: str,
    plan_id: str,
) -> str | None:
    """
    Deterministic backstop for the final completion check.

    If the agent created an onboarding plan but ended its turn without calling
    surface_need_for_review, the run would otherwise be marked FAILED even though
    the plan, brief, vectors, and strategy all exist — and the CSM would never see
    a review card. This does NOT make the agent less autonomous: it only fires when
    the agent already produced a plan, and surface_need_for_review is idempotent
    (it reuses an existing plan_approval_required need rather than duplicating).

    Returns the surfaced need_id, or None if surfacing failed.
    """
    from tools.database_tool import normalize_uuid
    from .tools import surface_need_for_review

    try:
        dc = get_dataconnect_client()
        plan_result = await dc.execute_query("GetAiPlan", {"id": normalize_uuid(plan_id)})
        plan = plan_result.get("aiPlan") or {}

        milestone_count = plan.get("milestoneCount") or 1
        playbook_name = plan.get("archetypeName") or "onboarding playbook"

        result = await surface_need_for_review(
            workspace_id=workspace_id,
            customer_id=customer_id,
            customer_name=customer_name,
            plan_id=plan_id,
            milestone_count=milestone_count,
            playbook_name=playbook_name,
        )
        if result.get("status") in ("surfaced",) or result.get("id"):
            logger.info(
                "need_surfaced_via_backstop",
                plan_id=plan_id,
                need_id=result.get("id"),
            )
            return result.get("id")

        logger.error("backstop_surface_failed", plan_id=plan_id, result=result)
        return None
    except Exception as e:
        logger.error("ensure_need_surfaced_failed", plan_id=plan_id, error=str(e))
        return None


# =============================================================================
# Main Entry Points
# =============================================================================

async def run_handoff_auto(
    workspace_id: str,
    customer_id: str,
    trigger_type: str = "manual",
    triggered_by: str | None = None,
) -> HandoffAutoResponse:
    """
    Run the handoff agent for a customer using ADK.

    Args:
        workspace_id: The workspace UUID
        customer_id: The customer UUID
        trigger_type: How triggered (manual, webhook, poll, setup_wizard)
        triggered_by: Who/what triggered it

    Returns:
        HandoffAutoResponse with status, IDs, and any pause information
    """
    dc = get_dataconnect_client()
    run_service = AgentRunService(dc, workspace_id)
    firestore = get_firestore_service()

    # Get customer name
    customer = await dc.get_customer(customer_id)
    customer_name = customer.get("name", "Unknown") if customer else "Unknown"

    # Create AgentRun record
    run = await run_service.create_run(
        agent_name="handoff_auto",
        trigger_type=trigger_type,
        triggered_by=triggered_by,
        input_params={"customer_id": customer_id},
    )
    run_id = str(run["id"])

    bind_context(
        run_id=run_id,
        workspace_id=workspace_id,
        customer_id=customer_id,
        agent="handoff_auto",
    )

    logger.info(
        "handoff_agent_started",
        trigger_type=trigger_type,
        customer_name=customer_name,
    )

    try:
        # Set run context for tools (inside try block for proper cleanup)
        set_run_context(run_id)

        # Mark run as started
        await run_service.start_run(run_id)
        await firestore.update_agent_status(
            run_id=run_id,
            status="running",
            step="starting",
            progress_pct=10,
            message="Starting handoff processing...",
        )
        # Create ADK agent with context
        agent = create_handoff_agent(customer_id, workspace_id, customer_name)

        # Create session
        session = await _session_service.create_session(
            app_name="handoff_auto",
            user_id=workspace_id,
            state={
                "run_id": run_id,
                "workspace_id": workspace_id,
                "customer_id": customer_id,
                "customer_name": customer_name,
            },
        )

        # Create runner
        runner = Runner(
            agent=agent,
            app_name="handoff_auto",
            session_service=_session_service,
        )

        # Initial message
        initial_message = types.Content(
            role="user",
            parts=[types.Part(text=f"Process handoff for customer: {customer_name}")],
        )

        # Run agent - ADK handles the conversation loop
        result = {
            "run_id": run_id,
            "status": AgentStatus.RUNNING.value,
            "customer_id": customer_id,
            "plan_id": None,
            "need_id": None,
        }

        # Run agent with automatic recovery for malformed function calls
        async for event in _run_with_recovery(
            runner=runner,
            user_id=workspace_id,
            session_id=session.id,
            initial_message=initial_message,
            workspace_id=workspace_id,
            customer_id=customer_id,
            customer_name=customer_name,
            max_recovery_attempts=2,
        ):
            # Check for HITL pause signal (set by pause_for_human_input tool)
            paused, questions = get_pause_state()
            if paused:
                result["status"] = AgentStatus.WAITING_FOR_INPUT.value
                result["paused_for_input"] = True
                result["questions"] = [q.model_dump() for q in questions]
                logger.info("agent_paused", question_count=len(questions))
                break

            # Check for final response
            if event.is_final_response():
                # Get result IDs from context variables (set by tools)
                plan_id, need_id = get_result_ids()

                # Deterministic backstop: the agent built a plan but ended its turn
                # without surfacing the review need. Surface it so the CSM sees it.
                if plan_id and not need_id:
                    logger.warning("plan_without_need_using_backstop", plan_id=plan_id)
                    need_id = await _ensure_need_surfaced(
                        workspace_id, customer_id, customer_name, plan_id
                    )

                result["plan_id"] = plan_id
                result["need_id"] = need_id

                if plan_id and need_id:
                    result["status"] = AgentStatus.COMPLETED.value
                else:
                    # Check pause state one more time
                    paused, questions = get_pause_state()
                    if paused:
                        result["status"] = AgentStatus.WAITING_FOR_INPUT.value
                        result["paused_for_input"] = True
                        result["questions"] = [q.model_dump() for q in questions]
                    else:
                        result["status"] = AgentStatus.FAILED.value
                        result["error"] = "Agent finished without completing all steps"
                break

        # Update run status based on result
        if result["status"] == AgentStatus.COMPLETED.value:
            await run_service.complete_run(
                run_id,
                result=result,
                customer_id=customer_id,
                plan_id=result.get("plan_id"),
            )
            await firestore.update_agent_status(
                run_id=run_id,
                status="completed",
                step="done",
                progress_pct=100,
                message="Handoff complete! Plan ready for review.",
            )
            logger.info(
                "handoff_agent_completed",
                plan_id=result.get("plan_id"),
                need_id=result.get("need_id"),
            )
        elif result["status"] == AgentStatus.WAITING_FOR_INPUT.value:
            await firestore.update_agent_status(
                run_id=run_id,
                status="waiting",
                step="waiting_for_input",
                progress_pct=50,
                message="Waiting for human input...",
            )
            logger.info("handoff_agent_paused")
        else:
            await run_service.fail_run(run_id, error_message=result.get("error", "Unknown"))
            await firestore.update_agent_status(
                run_id=run_id,
                status="failed",
                step="error",
                progress_pct=0,
                message=result.get("error", "Agent failed"),
            )
            logger.error("handoff_agent_failed", error=result.get("error"))

        return _to_response(result)

    except Exception as e:
        logger.exception("handoff_agent_error", error=str(e))
        await run_service.fail_run(run_id, error_message=str(e))
        await firestore.update_agent_status(
            run_id=run_id,
            status="failed",
            step="error",
            progress_pct=0,
            message=str(e),
        )
        return _to_response({
            "run_id": run_id,
            "status": AgentStatus.FAILED.value,
            "error": str(e),
        })

    finally:
        clear_pause_state()
        clear_context()


async def resume_handoff_auto(
    run_id: str,
    answers: dict[str, Any],
    workspace_id: str | None = None,
) -> HandoffAutoResponse:
    """
    Resume a paused agent run with provided answers.

    Args:
        run_id: The paused run UUID
        answers: Answers to the clarifying questions
        workspace_id: Optional workspace ID (looked up if not provided)

    Returns:
        HandoffAutoResponse with updated status
    """
    dc = get_dataconnect_client()
    run = await dc.get_agent_run(run_id)

    if not run:
        return _to_response({
            "run_id": run_id,
            "status": AgentStatus.FAILED.value,
            "error": "Run not found",
        })

    if not workspace_id:
        workspace_id = run.get("workspace", {}).get("id")
        if not workspace_id:
            return _to_response({
                "run_id": run_id,
                "status": AgentStatus.FAILED.value,
                "error": "Run has no workspace",
            })

    if run["status"] not in ("waiting_for_input", "resuming"):
        return _to_response({
            "run_id": run_id,
            "status": AgentStatus.FAILED.value,
            "error": f"Run is not paused (status: {run['status']})",
        })

    run_service = AgentRunService(dc, workspace_id)
    firestore = get_firestore_service()

    # Get customer info
    import json
    input_params = {}
    if run.get("inputParams"):
        try:
            input_params = json.loads(run["inputParams"])
        except (json.JSONDecodeError, TypeError):
            pass

    customer_id = input_params.get("customer_id") or run.get("customer", {}).get("id")
    if not customer_id:
        return _to_response({
            "run_id": run_id,
            "status": AgentStatus.FAILED.value,
            "error": "No customer_id in run context",
        })

    customer = await dc.get_customer(customer_id)
    customer_name = customer.get("name", "Unknown") if customer else "Unknown"

    bind_context(
        run_id=run_id,
        workspace_id=workspace_id,
        customer_id=customer_id,
        agent="handoff_auto_resume",
    )

    logger.info("handoff_agent_resuming", answer_count=len(answers))

    try:
        # Set run context for tools (inside try block for proper cleanup)
        set_run_context(run_id)

        # Transition to resuming then running
        await run_service.resume_from_input(run_id, answers)
        await run_service.mark_running_after_resume(run_id)

        await firestore.update_agent_status(
            run_id=run_id,
            status="running",
            step="resuming",
            progress_pct=60,
            message="Processing your answers...",
        )
        # Create agent with context
        agent = create_handoff_agent(customer_id, workspace_id, customer_name)

        # Create new session for resume (ADK sessions are stateless for us)
        session = await _session_service.create_session(
            app_name="handoff_auto",
            user_id=workspace_id,
            state={
                "run_id": run_id,
                "workspace_id": workspace_id,
                "customer_id": customer_id,
                "customer_name": customer_name,
                "hitl_answers": answers,  # Include answers in state
            },
        )

        # Create runner
        runner = Runner(
            agent=agent,
            app_name="handoff_auto",
            session_service=_session_service,
        )

        # Build resume message with existing artifact context
        questions_text = ""
        if run.get("clarifyingQuestions"):
            try:
                questions = json.loads(run["clarifyingQuestions"])
                questions_text = "\n".join([
                    f"- {q.get('question', q.get('field', 'Unknown'))}"
                    for q in questions
                ])
            except (json.JSONDecodeError, TypeError):
                pass

        answers_text = "\n".join([f"- {k}: {v}" for k, v in answers.items()])

        # Query for existing artifacts to inject context
        existing_artifacts = await _get_existing_artifacts(dc, customer_id)
        artifacts_text = _format_existing_artifacts(existing_artifacts)

        resume_message = types.Content(
            role="user",
            parts=[types.Part(text=f"""You previously paused for human input. Answers are ready.

**Questions you asked:**
{questions_text or "No questions recorded"}

**Answers provided:**
{answers_text}

{artifacts_text}

**IMPORTANT**: Check what already exists before creating anything new. The tools will prevent duplicates, but you should avoid unnecessary work. If a brief exists, update it rather than recreating. If a plan exists, surface it for review rather than regenerating.

Continue with the handoff workflow:
1. If brief exists, update it with clarified information. If not, create it.
2. Set customer goals if provided in the answers
3. If plan exists, proceed to surfacing. If not, generate the plan.
4. Surface for CSM review (if not already surfaced)
""")],
        )

        result = {
            "run_id": run_id,
            "status": AgentStatus.RUNNING.value,
            "customer_id": customer_id,
            "plan_id": None,
            "need_id": None,
            "resumed_from_pause": True,
        }

        # Run agent with automatic recovery for malformed function calls
        async for event in _run_with_recovery(
            runner=runner,
            user_id=workspace_id,
            session_id=session.id,
            initial_message=resume_message,
            workspace_id=workspace_id,
            customer_id=customer_id,
            customer_name=customer_name,
            max_recovery_attempts=2,
        ):
            paused, questions = get_pause_state()
            if paused:
                result["status"] = AgentStatus.WAITING_FOR_INPUT.value
                result["paused_for_input"] = True
                result["questions"] = [q.model_dump() for q in questions]
                break

            if event.is_final_response():
                # Get result IDs from context variables (set by tools)
                plan_id, need_id = get_result_ids()

                # Deterministic backstop (same rationale as run_handoff_auto)
                if plan_id and not need_id:
                    logger.warning("resume_plan_without_need_using_backstop", plan_id=plan_id)
                    need_id = await _ensure_need_surfaced(
                        workspace_id, customer_id, customer_name, plan_id
                    )

                result["plan_id"] = plan_id
                result["need_id"] = need_id

                if plan_id and need_id:
                    result["status"] = AgentStatus.COMPLETED.value
                else:
                    paused, questions = get_pause_state()
                    if paused:
                        result["status"] = AgentStatus.WAITING_FOR_INPUT.value
                        result["paused_for_input"] = True
                        result["questions"] = [q.model_dump() for q in questions]
                    else:
                        result["status"] = AgentStatus.FAILED.value
                        result["error"] = "Agent finished without completing"
                break

        # Update status
        if result["status"] == AgentStatus.COMPLETED.value:
            await run_service.complete_run(
                run_id,
                result=result,
                customer_id=customer_id,
                plan_id=result.get("plan_id"),
            )
            await firestore.update_agent_status(
                run_id=run_id,
                status="completed",
                step="done",
                progress_pct=100,
                message="Handoff complete!",
            )
            logger.info("handoff_agent_resumed_completed", plan_id=result.get("plan_id"))
        elif result["status"] == AgentStatus.WAITING_FOR_INPUT.value:
            await firestore.update_agent_status(
                run_id=run_id,
                status="waiting",
                step="waiting_for_input",
                progress_pct=70,
                message="Need more information...",
            )
            logger.info("handoff_agent_paused_again")
        else:
            await run_service.fail_run(run_id, error_message=result.get("error", "Unknown"))
            await firestore.update_agent_status(
                run_id=run_id,
                status="failed",
                step="error",
                progress_pct=0,
                message=result.get("error", "Failed"),
            )
            logger.error("handoff_agent_resume_failed", error=result.get("error"))

        return _to_response(result)

    except Exception as e:
        logger.exception("handoff_agent_resume_error", error=str(e))
        await run_service.fail_run(run_id, error_message=str(e))
        await firestore.update_agent_status(
            run_id=run_id,
            status="failed",
            step="error",
            progress_pct=0,
            message=str(e),
        )
        return _to_response({
            "run_id": run_id,
            "status": AgentStatus.FAILED.value,
            "error": str(e),
        })

    finally:
        clear_pause_state()
        clear_context()


# =============================================================================
# Scheduler Functions
# =============================================================================

async def check_and_resume_waiting_runs(workspace_id: str) -> list[HandoffAutoResponse]:
    """Check for paused runs that have been answered and resume them."""
    dc = get_dataconnect_client()
    run_service = AgentRunService(dc, workspace_id)

    waiting_runs = await run_service.get_waiting_runs(agent_name="handoff_auto")

    results = []
    for run in waiting_runs:
        try:
            run_id = str(run["id"])

            from services import get_hitl_answer_service
            answer_service = get_hitl_answer_service(workspace_id)
            answers = await answer_service.get_answers(run_id)

            if not answers and run.get("blocking_need_id"):
                answers = await _extract_answers_from_need(run["blocking_need_id"])

            if answers:
                result = await resume_handoff_auto(
                    run_id=run_id,
                    answers=answers,
                    workspace_id=workspace_id,
                )
                results.append(result)
        except Exception as e:
            logger.error("auto_resume_failed", run_id=str(run["id"]), error=str(e))

    return results


async def handle_timed_out_runs(
    workspace_id: str,
    timeout_hours: int = 24,
) -> list[HandoffAutoResponse]:
    """Handle runs that have been waiting too long."""
    dc = get_dataconnect_client()
    run_service = AgentRunService(dc, workspace_id)

    timed_out = await run_service.get_timed_out_runs(timeout_hours=timeout_hours)

    results = []
    for run in timed_out:
        try:
            settings_result = await dc.execute_query(
                "GetWorkspaceAgentSettings",
                {"workspaceId": workspace_id, "agentName": "handoff_auto"},
            )

            settings_list = settings_result.get("workspaceAgentSettings", [])
            fallback_on_timeout = settings_list[0].get("fallbackOnTimeout", False) if settings_list else False

            if fallback_on_timeout:
                result = await resume_handoff_auto(
                    run_id=str(run["id"]),
                    answers={},
                    workspace_id=workspace_id,
                )
                results.append(result)
            else:
                await run_service.fail_run(
                    str(run["id"]),
                    f"Timed out after {timeout_hours} hours without response",
                )
                results.append(HandoffAutoResponse(
                    run_id=str(run["id"]),
                    status=AgentStatus.FAILED,
                    error=f"Timed out after {timeout_hours} hours",
                ))
        except Exception as e:
            logger.error("timeout_handling_failed", run_id=str(run["id"]), error=str(e))

    return results


# =============================================================================
# Helpers
# =============================================================================

async def _get_existing_artifacts(dc, customer_id: str) -> dict[str, Any]:
    """
    Query for existing artifacts created for this customer.

    Used when resuming to tell the agent what already exists.
    """
    from tools.database_tool import normalize_uuid
    normalized_customer_id = normalize_uuid(customer_id)

    artifacts = {
        "brief": None,
        "plan": None,
        "need": None,
    }

    try:
        # Check for existing brief
        brief_result = await dc.execute_query(
            "GetLatestHandoffBriefForCustomer",
            {"customerId": normalized_customer_id},
        )
        briefs = brief_result.get("handoffBriefs", [])
        if briefs:
            artifacts["brief"] = {
                "id": briefs[0].get("id"),
                "captured_at": briefs[0].get("capturedAt"),
            }
    except Exception as e:
        logger.warning("get_existing_brief_failed", error=str(e))

    try:
        # Check for existing plan
        plan_result = await dc.execute_query(
            "GetExistingPendingPlan",
            {"customerId": normalized_customer_id},
        )
        plans = plan_result.get("aiPlans", [])
        if plans:
            artifacts["plan"] = {
                "id": plans[0].get("id"),
                "headline": plans[0].get("headline"),
                "milestone_count": plans[0].get("milestoneCount"),
            }
    except Exception as e:
        logger.warning("get_existing_plan_failed", error=str(e))

    try:
        # Check for existing plan_approval_required need
        from core.types import NeedType
        need_result = await dc.execute_query(
            "GetExistingNeedByType",
            {
                "customerId": normalized_customer_id,
                "needType": NeedType.PLAN_APPROVAL_REQUIRED.value,
            },
        )
        needs = need_result.get("needs", [])
        if needs:
            artifacts["need"] = {
                "id": needs[0].get("id"),
                "headline": needs[0].get("headline"),
            }
    except Exception as e:
        logger.warning("get_existing_need_failed", error=str(e))

    return artifacts


def _format_existing_artifacts(artifacts: dict[str, Any]) -> str:
    """Format existing artifacts as context for the resume prompt."""
    lines = []

    if artifacts.get("brief"):
        lines.append(f"- Handoff Brief: EXISTS (id: {artifacts['brief']['id']})")
    else:
        lines.append("- Handoff Brief: NOT CREATED YET")

    if artifacts.get("plan"):
        plan = artifacts["plan"]
        lines.append(f"- Onboarding Plan: EXISTS (id: {plan['id']}, {plan.get('milestone_count', '?')} milestones)")
    else:
        lines.append("- Onboarding Plan: NOT CREATED YET")

    if artifacts.get("need"):
        lines.append(f"- Plan Review Need: EXISTS (id: {artifacts['need']['id']})")
    else:
        lines.append("- Plan Review Need: NOT SURFACED YET")

    if not any(artifacts.values()):
        return "**Existing Artifacts:** None found - this appears to be a fresh start."

    return "**Existing Artifacts (from your prior work):**\n" + "\n".join(lines)


async def _extract_answers_from_need(need_id: str) -> dict[str, Any] | None:
    """Extract answers from a resolved need."""
    dc = get_dataconnect_client()

    run_result = await dc.execute_query(
        "GetAgentRunByBlockingNeed",
        {"blockingNeedId": need_id},
    )

    runs = run_result.get("agentRuns", [])
    if runs:
        run = runs[0]
        workspace = run.get("workspace", {})

        from services import get_hitl_answer_service
        answer_service = get_hitl_answer_service(workspace.get("id"))
        answers = await answer_service.get_answers(str(run["id"]))

        if answers:
            return answers

    # Fallback: check need_recommendations
    rec_result = await dc.execute_query(
        "GetNeedRecommendation",
        {"needId": need_id},
    )

    recs = rec_result.get("needRecommendations", [])
    if recs and recs[0].get("rationale"):
        return {"raw_answer": recs[0]["rationale"]}

    return None


def _to_response(result: dict[str, Any]) -> HandoffAutoResponse:
    """Convert internal result dict to HandoffAutoResponse."""
    status = result.get("status", AgentStatus.FAILED.value)
    if isinstance(status, str):
        try:
            status = AgentStatus(status)
        except ValueError:
            logger.warning(
                "unknown_agent_status",
                raw_status=status,
                run_id=result.get("run_id"),
            )
            status = AgentStatus.FAILED

    confidence = None
    if result.get("confidence"):
        confidence = ConfidenceAssessment(**result["confidence"])

    return HandoffAutoResponse(
        run_id=result.get("run_id", "unknown"),
        status=status,
        customer_id=result.get("customer_id"),
        brief_id=result.get("brief_id"),
        plan_id=result.get("plan_id"),
        need_id=result.get("need_id"),
        confidence=confidence,
        paused_for_questions=result.get("questions"),
        error=result.get("error"),
        used_fallback=result.get("used_fallback", False),
    )

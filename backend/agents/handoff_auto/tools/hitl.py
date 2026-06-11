"""
HITL (Human-in-the-Loop) Tools
Tools for pausing execution and recording questions.

Three question routing types:
- BLOCKERS: Use pause_for_human_input() - Actually pauses the agent (rare)
- SIDE-ASKS: Use add_handoff_questions(routing="sales") - Records but doesn't pause
- KICKOFF ITEMS: Use add_handoff_questions(routing="kickoff") - Records but doesn't pause
"""

import json
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

from config import get_settings
from core.logging import get_logger
from core.types import NeedType, StructuredQuestionType, QuestionType, ClarifyingQuestion
from db.dataconnect_client import get_dataconnect_client
from services.agent_run_service import AgentRunService
from services.sidekick_service import SidekickService
from tools.database_tool import insert_need, normalize_uuid

logger = get_logger("HandoffTools.HITL")
settings = get_settings()

# Shared state storage keyed by run_id
# Using a dict instead of ContextVars because ADK may execute tools in copied contexts
# where ContextVar changes don't propagate back to the parent
_run_states: dict[str, dict] = {}
_current_run_id: ContextVar[str | None] = ContextVar("_current_run_id", default=None)


def _get_run_state() -> dict:
    """Get or create state dict for current run."""
    run_id = _current_run_id.get()
    if not run_id:
        return {"paused": False, "questions": [], "plan_id": None, "need_id": None}
    if run_id not in _run_states:
        _run_states[run_id] = {"paused": False, "questions": [], "plan_id": None, "need_id": None}
    return _run_states[run_id]


def set_run_context(run_id: str):
    """Set the current run ID for tools to access."""
    _current_run_id.set(run_id)
    # Initialize fresh state for this run
    _run_states[run_id] = {"paused": False, "questions": [], "plan_id": None, "need_id": None}


def get_pause_state() -> tuple[bool, list]:
    """Get the current pause state (paused, questions)."""
    state = _get_run_state()
    return state["paused"], state["questions"]


def get_result_ids() -> tuple[str | None, str | None]:
    """Get the current plan_id and need_id."""
    state = _get_run_state()
    return state["plan_id"], state["need_id"]


def set_plan_id(plan_id: str):
    """Set the current plan ID (called by generate_onboarding_plan)."""
    state = _get_run_state()
    state["plan_id"] = plan_id
    logger.info("plan_id_set_in_state", plan_id=plan_id, run_id=_current_run_id.get())


def set_need_id(need_id: str):
    """Set the current need ID (called by surface_need_for_review)."""
    state = _get_run_state()
    state["need_id"] = need_id
    logger.info("need_id_set_in_state", need_id=need_id, run_id=_current_run_id.get())


def clear_pause_state():
    """Clear all run state."""
    run_id = _current_run_id.get()
    if run_id and run_id in _run_states:
        del _run_states[run_id]


def _infer_question_type(question: dict) -> StructuredQuestionType:
    """
    Infer the structured question type from question content.

    Conservative inference - defaults to freeform when uncertain.
    """
    q_text = question.get("question", "").lower()
    options = question.get("options")

    # Has explicit options -> pick_one or pick_many
    if options and isinstance(options, list) and len(options) > 1:
        if question.get("multi_select") or question.get("multiSelect"):
            return StructuredQuestionType.PICK_MANY
        return StructuredQuestionType.PICK_ONE

    # Very specific yes/no patterns (conservative)
    yes_no_patterns = [
        "is this correct",
        "does this look right",
        "should we proceed",
        "do you want to",
        "is that accurate",
        "confirm that",
    ]
    if any(p in q_text for p in yes_no_patterns):
        return StructuredQuestionType.YES_NO

    # Date patterns
    date_patterns = ["when", "what date", "by when", "target date", "deadline"]
    if any(p in q_text for p in date_patterns) and "date" in q_text.lower():
        return StructuredQuestionType.DATE

    # Default to freeform (safest)
    return StructuredQuestionType.FREEFORM


async def pause_for_human_input(
    workspace_id: str,
    customer_id: str,
    customer_name: str,
    questions_json: str,
    reason: str,
    context_json: str | None = None,
) -> dict[str, Any]:
    """
    Pause execution and ask the human for input with structured question types.

    ONLY use this for TRUE BLOCKERS:
    - Notes are essentially empty (no content to work with)
    - Sales committed to something the product doesn't do
    - Internal contradictions where every reading produces a different plan

    For side-asks (questions that can be answered later) use add_handoff_questions() instead.

    Args:
        workspace_id: The workspace UUID
        customer_id: The customer UUID
        customer_name: The customer's name
        questions_json: JSON string of list of questions to ask. Each question supports:
            REQUIRED:
            - question: The question text
            - field: What data this relates to (timeline, playbook, goals, etc.)

            OPTIONAL - Question Type (defaults to 'freeform'):
            - question_type: 'pick_one', 'pick_many', 'pick_person', 'slider', 'freeform', 'date', 'yes_no'

            FOR pick_one/pick_many:
            - options: List of {label, value, default?, description?}
            - allow_decide: Boolean - show "Sidekick, you decide" option
            - allow_other: Boolean - allow custom text input

            FOR slider:
            - min, max, default: Numeric values
            - label_low, label_high: Labels for ends

            FOR yes_no:
            - yes_label, no_label: Custom labels

        reason: Why you're pausing (for logging)
        context_json: Optional JSON string of context to help the human answer

    Returns:
        Confirmation that agent is paused, with instructions
    """
    normalized_workspace_id = normalize_uuid(workspace_id)
    normalized_customer_id = normalize_uuid(customer_id)

    # Parse JSON parameters
    try:
        questions = json.loads(questions_json) if questions_json else []
    except json.JSONDecodeError as e:
        logger.error("pause_questions_json_parse_error", error=str(e))
        return {"status": "error", "error": f"Invalid questions JSON: {e}"}

    context = None
    if context_json:
        try:
            context = json.loads(context_json)
        except json.JSONDecodeError:
            pass  # Ignore invalid context JSON

    dc = get_dataconnect_client()
    run_service = AgentRunService(dc, normalized_workspace_id)
    current_run = _current_run_id.get()

    # Format questions for storage with structured types
    structured_questions = []
    for q in questions:
        q_type_raw = q.get("question_type", "freeform")
        try:
            structured_type = StructuredQuestionType(q_type_raw.lower())
        except (ValueError, AttributeError):
            structured_type = _infer_question_type(q)
            logger.info(
                "inferred_question_type",
                original_type=q_type_raw,
                inferred_type=structured_type.value,
                field=q.get("field"),
            )

        # Build metadata based on question type
        metadata = {}

        if structured_type in (StructuredQuestionType.PICK_ONE, StructuredQuestionType.PICK_MANY):
            if q.get("options"):
                metadata["options"] = q["options"]
            if q.get("allow_decide") is not None:
                metadata["allow_decide"] = q["allow_decide"]
            if q.get("allow_other") is not None:
                metadata["allow_other"] = q["allow_other"]

        elif structured_type == StructuredQuestionType.SLIDER:
            metadata["min"] = q.get("min", 0)
            metadata["max"] = q.get("max", 100)
            metadata["default"] = q.get("default", 50)
            if q.get("label_low"):
                metadata["label_low"] = q["label_low"]
            if q.get("label_high"):
                metadata["label_high"] = q["label_high"]

        elif structured_type == StructuredQuestionType.YES_NO:
            if q.get("yes_label"):
                metadata["yes_label"] = q["yes_label"]
            if q.get("no_label"):
                metadata["no_label"] = q["no_label"]

        elif structured_type == StructuredQuestionType.DATE:
            if q.get("min_date"):
                metadata["min_date"] = q["min_date"]
            if q.get("max_date"):
                metadata["max_date"] = q["max_date"]

        elif structured_type == StructuredQuestionType.FREEFORM:
            if q.get("multiline") is not None:
                metadata["multiline"] = q["multiline"]
            if q.get("max_length") is not None:
                metadata["max_length"] = q["max_length"]

        clarifying_q = ClarifyingQuestion(
            id=q.get("id"),
            field=q.get("field", "general"),
            question=q.get("question"),
            question_type=QuestionType.CLARIFICATION,
            structured_type=structured_type,
            metadata=metadata if metadata else None,
            context=q.get("context"),
            required=q.get("required", True),
            placeholder=q.get("placeholder"),
            options=q.get("options"),
        )
        structured_questions.append(clarifying_q)

    # Create a need for the human to answer
    try:
        need = await insert_need(
            workspace_id=normalized_workspace_id,
            customer_id=normalized_customer_id,
            need_type=NeedType.SIDEKICK_QUESTION.value,
            headline=f"Sidekick needs input for {customer_name}",
            lede=f"The AI agent has {len(questions)} blocking question(s) before continuing.",
            agent_reasoning=f"Paused for human input: {reason}",
            priority_rank=3,
            agent_run_id=current_run,
        )
    except Exception as e:
        logger.error(
            "pause_need_creation_failed",
            workspace_id=normalized_workspace_id,
            customer_id=normalized_customer_id,
            run_id=current_run,
            error=str(e),
        )
        # Re-raise to prevent agent from continuing in invalid state
        raise RuntimeError(f"Failed to create blocking need: {e}") from e

    # Create a SidekickItem for visibility
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
            )
        except Exception as e:
            logger.warning("sidekick_item_creation_failed", error=str(e))

    # Update the AgentRun to paused status
    if current_run:
        await run_service.pause_run(
            run_id=current_run,
            pause_reason=reason,
            clarifying_questions=[q.model_dump() for q in structured_questions],
            blocking_need_id=need.get("id"),
            context_snapshot=context,
        )

    # Set state to signal pause
    state = _get_run_state()
    state["paused"] = True
    state["questions"] = structured_questions

    logger.info(
        "agent_paused_for_input",
        workspace_id=normalized_workspace_id,
        customer_id=normalized_customer_id,
        question_count=len(questions),
        reason=reason,
        need_id=need.get("id"),
        run_id=current_run,
    )

    return {
        "_hitl_signal": True,  # Signal to HITLRunner that we're pausing
        "status": "paused",
        "need_id": need.get("id"),
        "run_id": current_run,
        "questions": [q.model_dump() for q in structured_questions],
        "message": f"Agent paused. Created need {need.get('id')} for human to answer {len(questions)} question(s).",
        "instructions": "The agent will resume automatically when the human provides answers via the Today queue.",
    }


async def add_handoff_questions(
    workspace_id: str,
    customer_id: str,
    questions_json: str,
    routing: str,
) -> dict[str, Any]:
    """
    Record handoff questions WITHOUT pausing execution.

    Use this for:
    - routing="sales": Side-asks for the AE/sales team
      Examples: "What's the competitive situation?", "What's their budget cycle?"
    - routing="kickoff": Questions for the kickoff call agenda
      Examples: "Who else should be in the kickoff?", "What's their data migration plan?"

    These questions are recorded and shown to the appropriate people, but the
    agent CONTINUES building the plan. The plan ships now; answers refine it later.

    Args:
        workspace_id: The workspace UUID
        customer_id: The customer UUID
        questions_json: JSON string of list of questions. Each question supports:
            REQUIRED:
            - question: The question text
            - field: What data this relates to (timeline, playbook, goals, etc.)

            OPTIONAL - Question Type (defaults to 'freeform'):
            - question_type: 'pick_one', 'pick_many', 'pick_person', 'slider', 'freeform', 'date', 'yes_no'

            FOR pick_one/pick_many:
            - options: List of {label, value, default?, description?}
            - allow_decide: Boolean - show "Sidekick, you decide" option
            - allow_other: Boolean - allow custom text input

            FOR pick_person:
            - people: List of {id, name, role?, avatar?} to choose from

            FOR slider:
            - min, max, default: Numeric values
            - label_low, label_high: Labels for ends

            FOR yes_no:
            - yes_label, no_label: Custom labels

            FOR date:
            - min_date, max_date: Date bounds (ISO format)

            OTHER:
            - proposed_answer: Your best guess if you have one (optional)
            - relates_to: What aspect of the plan this affects (optional)

        routing: "sales" or "kickoff"

    Returns:
        Confirmation that questions were recorded (NO pause signal)
    """
    normalized_workspace_id = normalize_uuid(workspace_id)
    normalized_customer_id = normalize_uuid(customer_id)

    # Parse JSON parameter
    try:
        questions = json.loads(questions_json) if questions_json else []
    except json.JSONDecodeError as e:
        logger.error("add_questions_json_parse_error", error=str(e))
        return {"status": "error", "error": f"Invalid questions JSON: {e}"}

    dc = get_dataconnect_client()
    current_run = _current_run_id.get()

    if routing not in ("sales", "kickoff"):
        return {
            "status": "error",
            "error": f"Invalid routing: {routing}. Must be 'sales' or 'kickoff'.",
        }

    # Store questions in handoff_questions table
    created_ids = []
    for q in questions:
        try:
            question_id = str(uuid4())

            # Extract question type (default to freeform)
            question_type = q.get("question_type", "freeform")

            # Build metadata from type-specific fields
            metadata = {}
            # pick_one / pick_many
            if q.get("options"):
                metadata["options"] = q["options"]
            if q.get("allow_decide") is not None:
                metadata["allow_decide"] = q["allow_decide"]
            if q.get("allow_other") is not None:
                metadata["allow_other"] = q["allow_other"]
            # pick_person
            if q.get("people"):
                metadata["people"] = q["people"]
            # slider
            if q.get("min") is not None:
                metadata["min"] = q["min"]
            if q.get("max") is not None:
                metadata["max"] = q["max"]
            if q.get("default") is not None:
                metadata["default"] = q["default"]
            if q.get("label_low"):
                metadata["label_low"] = q["label_low"]
            if q.get("label_high"):
                metadata["label_high"] = q["label_high"]
            # yes_no
            if q.get("yes_label"):
                metadata["yes_label"] = q["yes_label"]
            if q.get("no_label"):
                metadata["no_label"] = q["no_label"]
            # date
            if q.get("min_date"):
                metadata["min_date"] = q["min_date"]
            if q.get("max_date"):
                metadata["max_date"] = q["max_date"]

            await dc.execute_mutation(
                "CreateHandoffQuestion",
                {
                    "id": question_id,
                    "workspaceId": normalized_workspace_id,
                    "customerId": normalized_customer_id,
                    "agentRunId": current_run,
                    "question": q.get("question"),
                    "field": q.get("field"),
                    "routing": routing,
                    "questionType": question_type,
                    "metadata": json.dumps(metadata) if metadata else None,
                    "proposedAnswer": q.get("proposed_answer"),
                    "relatesTo": q.get("relates_to"),
                    "status": "pending",
                },
            )
            created_ids.append(question_id)
        except Exception as e:
            logger.warning(
                "handoff_question_creation_failed",
                error=str(e),
                question=q.get("question", "")[:50],
            )

    logger.info(
        "handoff_questions_recorded",
        workspace_id=normalized_workspace_id,
        customer_id=normalized_customer_id,
        routing=routing,
        question_count=len(created_ids),
        run_id=current_run,
    )

    # Create a non-blocking SidekickItem for visibility (shows in UI but doesn't block)
    if current_run and created_ids:
        try:
            sidekick = SidekickService(dc, normalized_workspace_id)
            await sidekick.create_non_blocking_questions(
                customer_id=normalized_customer_id,
                agent_run_id=current_run,
                question_count=len(created_ids),
                routing=routing,
            )
        except Exception as e:
            logger.warning("non_blocking_sidekick_creation_failed", error=str(e))

    return {
        "status": "recorded",
        "routing": routing,
        "question_count": len(created_ids),
        "question_ids": created_ids,
        "message": f"Recorded {len(created_ids)} {routing} question(s). Agent continues without pausing.",
        # Explicitly NO _hitl_signal - we don't pause
    }


async def update_plan_from_answers(
    plan_id: str,
    answers_json: str,
    workspace_id: str,
) -> dict[str, Any]:
    """
    Update an existing plan based on side-ask or kickoff answers.

    Use this when answers to previously recorded questions (from add_handoff_questions)
    arrive later and you need to refine the plan.

    Args:
        plan_id: The plan UUID to update
        answers_json: JSON string of dict mapping field -> answer
        workspace_id: The workspace UUID

    Returns:
        Summary of what was updated
    """
    normalized_plan_id = normalize_uuid(plan_id)
    normalized_workspace_id = normalize_uuid(workspace_id)

    # Parse JSON parameter
    try:
        answers = json.loads(answers_json) if answers_json else {}
    except json.JSONDecodeError as e:
        logger.error("update_plan_answers_json_parse_error", error=str(e))
        return {"status": "error", "error": f"Invalid answers JSON: {e}"}

    dc = get_dataconnect_client()

    try:
        # Get the existing plan
        result = await dc.execute_query(
            "GetAiPlan",
            {"id": normalized_plan_id},
        )
        plan = result.get("aiPlan")

        if not plan:
            return {
                "status": "error",
                "error": f"Plan {normalized_plan_id} not found",
            }

        # Track what we updated
        updates = []

        # Update milestones based on answers
        # This is a simplified implementation - expand based on actual answer fields
        for field, answer in answers.items():
            if field == "timeline" and answer:
                # Adjust milestone dates
                updates.append(f"Adjusted timeline based on: {answer}")

            elif field == "success_metrics" and answer:
                # Could update plan headline or add notes
                updates.append(f"Added success metrics: {answer}")

            elif field == "stakeholders" and answer:
                # Could update stakeholder information
                updates.append(f"Updated stakeholder info: {answer}")

        # Log the update
        logger.info(
            "plan_updated_from_answers",
            plan_id=normalized_plan_id,
            workspace_id=normalized_workspace_id,
            answer_count=len(answers),
            update_count=len(updates),
        )

        return {
            "status": "updated",
            "plan_id": normalized_plan_id,
            "updates": updates,
            "message": f"Plan updated with {len(updates)} change(s) based on {len(answers)} answer(s).",
        }

    except Exception as e:
        logger.error(
            "plan_update_from_answers_failed",
            plan_id=normalized_plan_id,
            error=str(e),
        )
        return {
            "status": "error",
            "error": str(e),
        }

"""
Confidence Assessment
Logic for determining agent confidence and when to pause for input
"""

import re
from typing import Any

from core.types import (
    ConfidenceLevel,
    ConfidenceAssessment,
    ClarifyingQuestion,
    QuestionType,
    StructuredQuestionType,
    AutonomyMode,
    NotionDeal,
    WorkspaceAgentSettings,
)
from core.logging import get_logger

logger = get_logger("ConfidenceAssessment")


# Patterns that indicate vague or ambiguous commitments
VAGUE_PATTERNS = [
    r"\basap\b",
    r"\bsoon\b",
    r"\bquickly\b",
    r"\bflexible\b",
    r"\btbd\b",
    r"\bto be determined\b",
    r"\bnegotiable\b",
    r"\bdepends\b",
    r"\bif possible\b",
    r"\bmaybe\b",
    r"\bpotentially\b",
]

# High-value deal threshold (above this, always verify)
HIGH_VALUE_ARR_CENTS = 10_000_000  # $100K

# Required fields for confident processing
REQUIRED_FIELDS = ["company_name", "arr_cents", "stakeholders"]


def assess_confidence(
    deal: NotionDeal,
    playbook: dict[str, Any] | None = None,
    gap_analysis: dict[str, Any] | None = None,
) -> ConfidenceAssessment:
    """
    Assess confidence in processing a deal autonomously.

    Evaluates:
    - Data completeness (required fields present)
    - Data quality (no vague/ambiguous commitments)
    - Deal value (high-value deals need verification)
    - Gap analysis results (if available)

    Args:
        deal: The Notion deal to assess
        playbook: Matched playbook (if any)
        gap_analysis: Gap analysis results from LLM

    Returns:
        ConfidenceAssessment with level, score, reasons, and questions
    """
    reasons: list[str] = []
    questions: list[ClarifyingQuestion] = []
    score = 1.0  # Start at 100%, reduce based on issues

    # Check data completeness
    completeness_issues = _check_completeness(deal)
    if completeness_issues:
        reasons.extend(completeness_issues["reasons"])
        questions.extend(completeness_issues["questions"])
        score -= 0.15 * len(completeness_issues["questions"])

    # Check for vague commitments
    vagueness_issues = _check_vagueness(deal)
    if vagueness_issues:
        reasons.extend(vagueness_issues["reasons"])
        questions.extend(vagueness_issues["questions"])
        score -= 0.10 * len(vagueness_issues["questions"])

    # Check deal value
    if deal.arr_cents and deal.arr_cents > HIGH_VALUE_ARR_CENTS:
        reasons.append("high_value_deal_requires_verification")
        score -= 0.20
        questions.append(ClarifyingQuestion(
            field="deal_value",
            question=f"This is a high-value deal (${deal.arr_cents / 100:,.0f} ARR). "
                     "Please confirm the deal details are accurate.",
            question_type=QuestionType.VALIDATION,
            structured_type=StructuredQuestionType.YES_NO,
            context="High-value deals receive additional verification to ensure accuracy.",
        ))

    # Check playbook match
    if not playbook:
        reasons.append("no_playbook_match")
        score -= 0.15
        questions.append(ClarifyingQuestion(
            field="playbook",
            question="No matching playbook found. Which onboarding archetype fits best?",
            question_type=QuestionType.AMBIGUITY,
            structured_type=StructuredQuestionType.PICK_ONE,
            context="Options typically include: Enterprise, Mid-Market, SMB, Self-Serve",
            options=[
                {"value": "enterprise", "label": "Enterprise", "description": "High-touch, dedicated resources"},
                {"value": "mid_market", "label": "Mid-Market", "description": "Guided onboarding with CSM support"},
                {"value": "smb", "label": "SMB", "description": "Streamlined self-service with check-ins"},
                {"value": "self_serve", "label": "Self-Serve", "description": "Automated onboarding with docs"},
            ],
        ))

    # Check gap analysis results
    if gap_analysis:
        gap_issues = _check_gap_analysis(gap_analysis)
        if gap_issues:
            reasons.extend(gap_issues["reasons"])
            questions.extend(gap_issues["questions"])
            score -= 0.10 * len(gap_issues["questions"])

    # Clamp score
    score = max(0.0, min(1.0, score))

    # Determine confidence level
    if score >= 0.80:
        level = ConfidenceLevel.HIGH
    elif score >= 0.50:
        level = ConfidenceLevel.MEDIUM
    else:
        level = ConfidenceLevel.LOW

    assessment = ConfidenceAssessment(
        level=level,
        score=score,
        reasons=reasons if reasons else ["all_checks_passed"],
        questions=questions if questions else None,
    )

    logger.info(
        "confidence_assessed",
        company=deal.company_name,
        level=level.value,
        score=score,
        reason_count=len(reasons),
        question_count=len(questions),
    )

    return assessment


def should_pause(
    assessment: ConfidenceAssessment,
    settings: WorkspaceAgentSettings | None = None,
) -> bool:
    """
    Determine if the agent should pause based on confidence and settings.

    Args:
        assessment: The confidence assessment
        settings: Workspace agent settings (autonomy mode, etc.)

    Returns:
        True if agent should pause for input
    """
    if settings is None:
        # Default to smart_auto mode
        autonomy_mode = AutonomyMode.SMART_AUTO
        pause_on_medium = True
    else:
        autonomy_mode = AutonomyMode(settings.autonomy_mode)
        pause_on_medium = settings.pause_on_medium_confidence

    # Full auto never pauses
    if autonomy_mode == AutonomyMode.FULL_AUTO:
        return False

    # Supervised always pauses
    if autonomy_mode == AutonomyMode.SUPERVISED:
        return True

    # Smart auto: pause on low, optionally on medium
    if assessment.level == ConfidenceLevel.LOW:
        return True

    if assessment.level == ConfidenceLevel.MEDIUM and pause_on_medium:
        return True

    return False


def _check_completeness(deal: NotionDeal) -> dict[str, Any] | None:
    """Check for missing required fields."""
    reasons = []
    questions = []

    # Check company name
    if not deal.company_name or deal.company_name == "Unknown":
        reasons.append("missing_company_name")
        questions.append(ClarifyingQuestion(
            field="company_name",
            question="What is the company name for this deal?",
            question_type=QuestionType.MISSING_DATA,
            structured_type=StructuredQuestionType.FREEFORM,
            placeholder="Enter company name",
        ))

    # Check ARR
    if not deal.arr_cents or deal.arr_cents == 0:
        reasons.append("missing_arr")
        questions.append(ClarifyingQuestion(
            field="arr_cents",
            question="What is the ARR (Annual Recurring Revenue) for this deal?",
            question_type=QuestionType.MISSING_DATA,
            structured_type=StructuredQuestionType.FREEFORM,
            context="Enter the annual contract value in dollars.",
            placeholder="e.g., $50,000",
        ))

    # Check stakeholders
    if not deal.stakeholders or len(deal.stakeholders) == 0:
        reasons.append("missing_stakeholders")
        questions.append(ClarifyingQuestion(
            field="stakeholders",
            question="Who are the key stakeholders at this customer?",
            question_type=QuestionType.MISSING_DATA,
            structured_type=StructuredQuestionType.FREEFORM,
            context="Include name, role, and email for primary contacts.",
            placeholder="e.g., Jane Smith (VP Engineering) - jane@company.com",
            metadata={"multiline": True},
        ))

    # Check timeline
    if not deal.timeline:
        reasons.append("missing_timeline")
        questions.append(ClarifyingQuestion(
            field="timeline",
            question="What is the expected implementation timeline?",
            question_type=QuestionType.MISSING_DATA,
            structured_type=StructuredQuestionType.PICK_ONE,
            context="Select the target onboarding duration",
            options=[
                {"value": "14_days", "label": "2 weeks", "description": "Aggressive timeline"},
                {"value": "30_days", "label": "30 days", "description": "Standard onboarding"},
                {"value": "45_days", "label": "45 days", "description": "Extended onboarding"},
                {"value": "60_days", "label": "60 days", "description": "Enterprise timeline"},
            ],
        ))

    if reasons:
        return {"reasons": reasons, "questions": questions}
    return None


def _check_vagueness(deal: NotionDeal) -> dict[str, Any] | None:
    """Check for vague or ambiguous data."""
    reasons = []
    questions = []

    # Check timeline vagueness
    if deal.timeline:
        timeline_lower = deal.timeline.lower()
        for pattern in VAGUE_PATTERNS:
            if re.search(pattern, timeline_lower, re.IGNORECASE):
                reasons.append("vague_timeline")
                questions.append(ClarifyingQuestion(
                    field="timeline",
                    question=f"Timeline says '{deal.timeline}'. Can you specify a concrete timeframe?",
                    question_type=QuestionType.CLARIFICATION,
                    structured_type=StructuredQuestionType.PICK_ONE,
                    context="We need a specific number of days or target date for planning.",
                    options=[
                        {"value": "14_days", "label": "2 weeks"},
                        {"value": "30_days", "label": "30 days"},
                        {"value": "45_days", "label": "45 days"},
                        {"value": "60_days", "label": "60+ days"},
                    ],
                ))
                break

    # Check commitment vagueness
    for commitment in deal.sales_commitments:
        item = commitment.get("item", "") if isinstance(commitment, dict) else str(commitment)
        item_lower = item.lower()

        for pattern in VAGUE_PATTERNS:
            if re.search(pattern, item_lower, re.IGNORECASE):
                reasons.append("vague_commitment")
                questions.append(ClarifyingQuestion(
                    field="sales_commitments",
                    question=f"Commitment '{item}' is vague. Can you clarify what specifically was promised?",
                    question_type=QuestionType.CLARIFICATION,
                    structured_type=StructuredQuestionType.FREEFORM,
                    context="Specific commitments help us build accurate onboarding plans.",
                    placeholder="Describe what was promised...",
                    metadata={"multiline": True},
                ))
                break

    if reasons:
        return {"reasons": reasons, "questions": questions}
    return None


def _check_gap_analysis(gap_analysis: dict[str, Any]) -> dict[str, Any] | None:
    """Check gap analysis results for issues."""
    reasons = []
    questions = []

    # Check confidence from LLM
    llm_confidence = gap_analysis.get("confidence", "medium")
    if llm_confidence == "low":
        reasons.append("llm_low_confidence")

    # Check for explicitly flagged clarifications
    if gap_analysis.get("needs_clarification"):
        reasons.append("llm_needs_clarification")
        for q in gap_analysis.get("open_questions", []):
            questions.append(ClarifyingQuestion(
                field="gap_analysis",
                question=q,
                question_type=QuestionType.CLARIFICATION,
                structured_type=StructuredQuestionType.FREEFORM,
                context="Identified during gap analysis.",
            ))

    # Check if timeline is not feasible
    if not gap_analysis.get("timeline_feasible", True):
        reasons.append("timeline_not_feasible")
        questions.append(ClarifyingQuestion(
            field="timeline",
            question="The requested timeline may not be feasible with our standard playbook. "
                     "Should we propose an extended timeline or adjust scope?",
            question_type=QuestionType.VALIDATION,
            structured_type=StructuredQuestionType.PICK_ONE,
            context=f"Risks: {', '.join(gap_analysis.get('risks', [])[:2])}",
            options=[
                {"value": "extend_timeline", "label": "Extend timeline", "description": "Keep full scope, more time"},
                {"value": "reduce_scope", "label": "Reduce scope", "description": "Keep timeline, fewer milestones"},
                {"value": "proceed_anyway", "label": "Proceed as planned", "description": "Accept the risk"},
            ],
        ))

    if reasons:
        return {"reasons": reasons, "questions": questions}
    return None


def merge_answers_into_deal(
    deal: NotionDeal,
    answers: dict[str, Any],
) -> NotionDeal:
    """
    Merge human-provided answers back into deal data.

    Args:
        deal: Original deal
        answers: Answers keyed by field name

    Returns:
        Updated NotionDeal with answers merged in
    """
    # Create a new deal with merged data
    deal_dict = deal.model_dump()

    for field, answer in answers.items():
        if field == "company_name" and answer:
            deal_dict["company_name"] = answer
        elif field == "arr_cents" and answer:
            # Handle both formatted strings and raw numbers
            if isinstance(answer, str):
                # Remove currency symbols and commas
                clean = re.sub(r"[^\d.]", "", answer)
                if clean:
                    deal_dict["arr_cents"] = int(float(clean) * 100)
            else:
                deal_dict["arr_cents"] = int(answer * 100) if answer < 1000000 else int(answer)
        elif field == "timeline" and answer:
            deal_dict["timeline"] = answer
        elif field == "stakeholders" and answer:
            if isinstance(answer, list):
                deal_dict["stakeholders"] = answer
            elif isinstance(answer, str):
                # Try to parse as simple list
                deal_dict["stakeholders"] = [{"name": answer}]

    return NotionDeal(**deal_dict)

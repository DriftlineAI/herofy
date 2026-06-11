"""
Signal Watcher Confidence Assessment
Logic for determining agent confidence in signal processing decisions
"""

from typing import Any

from core.types import (
    ConfidenceLevel,
    ConfidenceAssessment,
    ClarifyingQuestion,
    QuestionType,
    AutonomyMode,
    WorkspaceAgentSettings,
)
from core.logging import get_logger

from agents.signal_watcher.models import (
    ClassifiedSignal,
    ThreadMatch,
    NeedMatch,
    MatchType,
    Urgency,
)

logger = get_logger("SignalWatcherConfidence")


# Thresholds for confidence assessment
THREAD_MATCH_HIGH_THRESHOLD = 0.85
THREAD_MATCH_MEDIUM_THRESHOLD = 0.60
NEED_MATCH_HIGH_THRESHOLD = 0.80
NEED_MATCH_MEDIUM_THRESHOLD = 0.55


def assess_signal_confidence(
    signal: ClassifiedSignal,
    thread_match: ThreadMatch | None,
    need_match: NeedMatch | None,
) -> ConfidenceAssessment:
    """
    Assess confidence in processing a signal autonomously.

    Evaluates:
    - Classification confidence (need_type, sentiment)
    - Thread match quality (explicit vs inferred)
    - Need match quality
    - Signal urgency (urgent signals may need verification)
    - Customer resolution

    Args:
        signal: The classified signal to assess
        thread_match: Thread matching result (if any)
        need_match: Need matching result (if any)

    Returns:
        ConfidenceAssessment with level, score, reasons, and questions
    """
    reasons: list[str] = []
    questions: list[ClarifyingQuestion] = []
    score = 1.0  # Start at 100%, reduce based on issues

    # Check classification confidence
    if signal.classification:
        if signal.classification.confidence < 0.5:
            reasons.append("low_classification_confidence")
            score -= 0.20
            questions.append(ClarifyingQuestion(
                field="need_type",
                question=f"Signal classified as '{signal.classification.need_type}' but confidence is low. "
                         "What type of need does this represent?",
                question_type=QuestionType.AMBIGUITY,
                context=f"Subject: {signal.subject or '(no subject)'}",
            ))
    else:
        reasons.append("no_classification")
        score -= 0.25

    # Check thread match
    if thread_match:
        if thread_match.match_type == MatchType.EXPLICIT:
            # Explicit matches are high confidence
            pass
        elif thread_match.match_type == MatchType.INFERRED:
            if thread_match.confidence < THREAD_MATCH_HIGH_THRESHOLD:
                if thread_match.confidence < THREAD_MATCH_MEDIUM_THRESHOLD:
                    reasons.append("low_thread_match_confidence")
                    score -= 0.25
                    questions.append(ClarifyingQuestion(
                        field="thread_id",
                        question=f"This signal may belong to thread '{thread_match.thread_subject}' "
                                 f"(confidence: {thread_match.confidence:.0%}). Is this correct?",
                        question_type=QuestionType.VALIDATION,
                        context=f"Match reason: {thread_match.reason}",
                    ))
                else:
                    reasons.append("medium_thread_match_confidence")
                    score -= 0.10
    else:
        # No thread match - might be a new thread
        # This isn't necessarily bad, but worth noting
        reasons.append("no_thread_match")

    # Check need match confidence
    if need_match:
        if need_match.confidence < NEED_MATCH_HIGH_THRESHOLD:
            if need_match.confidence < NEED_MATCH_MEDIUM_THRESHOLD:
                reasons.append("low_need_match_confidence")
                score -= 0.20
                questions.append(ClarifyingQuestion(
                    field="need_id",
                    question=f"This signal may relate to existing need '{need_match.need_headline}' "
                             f"(confidence: {need_match.confidence:.0%}). Should we link them?",
                    question_type=QuestionType.VALIDATION,
                    context=f"Need type: {need_match.need_type or 'unknown'}",
                ))
            else:
                reasons.append("medium_need_match_confidence")
                score -= 0.10

    # Check for urgent signals without clear routing
    if signal.classification and signal.classification.urgency == Urgency.HIGH:
        if not thread_match and not need_match:
            reasons.append("urgent_signal_no_routing")
            score -= 0.15
            questions.append(ClarifyingQuestion(
                field="routing",
                question="This appears to be an urgent signal but we couldn't match it to "
                         "an existing thread or need. Should we create a new urgent need?",
                question_type=QuestionType.VALIDATION,
                context=f"Detected urgency indicators in: {signal.subject or signal.body[:100] if signal.body else 'content'}",
            ))

    # Check customer resolution
    if not signal.customer_id:
        reasons.append("unresolved_customer")
        score -= 0.15
        questions.append(ClarifyingQuestion(
            field="customer_id",
            question=f"Could not identify customer for sender '{signal.sender_email}'. "
                     "Which customer does this belong to?",
            question_type=QuestionType.MISSING_DATA,
            context="We match customers by email domain.",
        ))

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
        "signal_confidence_assessed",
        signal_id=signal.id,
        level=level.value,
        score=score,
        reason_count=len(reasons),
        question_count=len(questions),
    )

    return assessment


def should_pause_for_signal(
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


def assess_batch_confidence(
    signals: list[ClassifiedSignal],
    thread_matches: dict[str, ThreadMatch | None],
    need_matches: dict[str, NeedMatch | None],
) -> tuple[ConfidenceAssessment, list[str]]:
    """
    Assess confidence for a batch of signals.

    Returns overall confidence based on the lowest-confidence signal
    that requires attention.

    Args:
        signals: List of classified signals
        thread_matches: Thread matches by signal_id
        need_matches: Need matches by signal_id

    Returns:
        Tuple of (overall assessment, list of low-confidence signal IDs)
    """
    low_confidence_signals: list[str] = []
    all_reasons: list[str] = []
    all_questions: list[ClarifyingQuestion] = []
    min_score = 1.0

    for signal in signals:
        assessment = assess_signal_confidence(
            signal=signal,
            thread_match=thread_matches.get(signal.id),
            need_match=need_matches.get(signal.id),
        )

        if assessment.level == ConfidenceLevel.LOW:
            low_confidence_signals.append(signal.id)

        if assessment.score < min_score:
            min_score = assessment.score

        all_reasons.extend(assessment.reasons)
        if assessment.questions:
            all_questions.extend(assessment.questions)

    # Determine overall confidence level based on batch
    if min_score >= 0.80 and len(low_confidence_signals) == 0:
        level = ConfidenceLevel.HIGH
    elif min_score >= 0.50 and len(low_confidence_signals) <= len(signals) * 0.1:
        level = ConfidenceLevel.MEDIUM
    else:
        level = ConfidenceLevel.LOW

    # Deduplicate reasons
    unique_reasons = list(dict.fromkeys(all_reasons))

    overall_assessment = ConfidenceAssessment(
        level=level,
        score=min_score,
        reasons=unique_reasons[:10],  # Limit to 10 reasons
        questions=all_questions[:5] if all_questions else None,  # Limit to 5 questions
    )

    logger.info(
        "batch_confidence_assessed",
        signal_count=len(signals),
        low_confidence_count=len(low_confidence_signals),
        overall_level=level.value,
        overall_score=min_score,
    )

    return overall_assessment, low_confidence_signals

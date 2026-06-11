"""
Classification Patterns
Regex patterns and keywords for signal classification

Patterns are organized by:
1. Need Type (urgent_support, going_dark, etc.)
2. Sentiment (positive, negative, frustrated)
3. Urgency indicators

Design note: Patterns support fuzzy matching via word boundaries and
case-insensitive matching. Designed for easy transition to LLM hybrid.
"""

import re
from typing import NamedTuple


class PatternSet(NamedTuple):
    """Collection of patterns for a classification category."""
    patterns: list[str]  # Regex patterns
    keywords: list[str]  # Simple keyword matches
    weight: float  # How much this pattern set contributes to confidence


# =============================================================================
# NEED TYPE PATTERNS
# =============================================================================

URGENT_SUPPORT_PATTERNS = PatternSet(
    patterns=[
        r"\burgent\b",
        r"\basap\b",
        r"\bemergency\b",
        r"\bproduction\s+(down|issue|outage|broken)\b",
        r"\b(not\s+working|doesn'?t\s+work|stopped\s+working)\b",
        r"\bblocking\b",
        r"\bcritical\s+(bug|issue|error)\b",
        r"\bdown\s+since\b",
        r"\bbroken\b",
        r"\boutage\b",
    ],
    keywords=[
        "urgent", "asap", "emergency", "critical", "blocking",
        "down", "outage", "broken", "production issue",
    ],
    weight=1.0,
)

GOING_DARK_PATTERNS = PatternSet(
    patterns=[
        r"\bno\s+(response|reply|answer)\b",
        r"\bhaven'?t\s+heard\b",
        r"\bnot\s+respond(ing|ed)?\b",
        r"\b(silent|quiet)\s+for\b",
        r"\b\d+\s+days?\s+(ago|since)\b.*\bno\b",
        r"\bfollow\s*-?\s*up\b.*\bno\s+(response|reply)\b",
        r"\bghost(ed|ing)?\b",
    ],
    keywords=[
        "no response", "no reply", "haven't heard", "not responding",
        "silent", "follow up needed", "ghosted",
    ],
    weight=0.9,
)

FRUSTRATED_SIGNAL_PATTERNS = PatternSet(
    patterns=[
        r"\bfrustrat(ed|ing|ion)\b",
        r"\bdisappoint(ed|ing|ment)\b",
        r"\bunacceptable\b",
        r"\bridiculous\b",
        r"\b(very\s+)?(upset|unhappy|angry)\b",
        r"!!+",  # Multiple exclamation marks
        r"\bWAITING\b",  # ALL CAPS waiting
        r"\b(three|3)\s+(weeks?|months?)\b.*\b(still|waiting)\b",
        r"\bescalat(e|ion)\b",
        r"\bCTO|CEO|VP\b.*\b(asking|wants|escalate)\b",
    ],
    keywords=[
        "frustrated", "disappointed", "unacceptable", "ridiculous",
        "upset", "unhappy", "escalate", "escalation",
    ],
    weight=1.0,
)

POSITIVE_SIGNAL_PATTERNS = PatternSet(
    patterns=[
        r"\b(love|loving)\s+(it|the|this)\b",
        r"\b(great|amazing|awesome|fantastic|excellent)\s+(work|job|feature|product)\b",
        r"\bthank\s+you\b",
        r"\bgreat\s+news\b",
        r"\bahead\s+of\s+schedule\b",
        r"\bgoing\s+(great|well|smoothly)\b",
        r":tada:|:heart:|:clap:|:rocket:",  # Emoji patterns
        r"\bimpressed\b",
        r"\bexceed(ed|s)?\s+expectations?\b",
    ],
    keywords=[
        "love it", "great work", "amazing", "fantastic", "thank you",
        "impressed", "ahead of schedule", "great news",
    ],
    weight=0.8,
)

EXPANSION_SIGNAL_PATTERNS = PatternSet(
    patterns=[
        r"\b(more|additional)\s+seats?\b",
        r"\bexpand(ing)?\b.*\b(team|users?|seats?)\b",
        r"\bupgrade\b",
        r"\b(add|adding)\s+(users?|seats?|licenses?)\b",
        r"\bpricing\s+(for|on)\s+\d+",
        r"\b(grow|growing|scale|scaling)\b.*\b(team|usage)\b",
        r"\b\d+\s+to\s+\d+\s+seats?\b",
    ],
    keywords=[
        "more seats", "expand", "upgrade", "additional users",
        "add users", "pricing for", "scale up",
    ],
    weight=0.9,
)

CHECK_IN_DUE_PATTERNS = PatternSet(
    patterns=[
        r"\bcheck\s*-?\s*in\b",
        r"\bweek\s+\d+\b.*\b(review|update)\b",
        r"\bmonthly\s+(review|call|meeting)\b",
        r"\bquarterly\s+(review|business)\b",
        r"\bQBR\b",
        r"\bscheduled?\s+(call|meeting|review)\b",
    ],
    keywords=[
        "check-in", "check in", "weekly review", "monthly review",
        "QBR", "scheduled call",
    ],
    weight=0.6,
)

STALLED_MILESTONE_PATTERNS = PatternSet(
    patterns=[
        r"\bstuck\s+(on|at)\b",
        r"\bblocked\s+(by|on)\b",
        r"\bcan'?t\s+proceed\b",
        r"\bwaiting\s+(for|on)\b.*\b(input|access|approval)\b",
        r"\bmilestone\s+\d+\b.*\b(delayed|blocked)\b",
        r"\bpush(ed|ing)?\s+(back|out)\b.*\b(timeline|date)\b",
    ],
    keywords=[
        "stuck", "blocked", "can't proceed", "delayed",
        "waiting for", "push back",
    ],
    weight=0.8,
)

# =============================================================================
# SENTIMENT PATTERNS
# =============================================================================

NEGATIVE_SENTIMENT_PATTERNS = PatternSet(
    patterns=[
        r"\b(issue|problem|error|bug)\b",
        r"\bnot\s+(working|happy|satisfied)\b",
        r"\b(concern|worried|nervous)\b",
        r"\b(bad|poor|terrible)\s+(experience|service)\b",
        r"\bregret\b",
    ],
    keywords=[
        "issue", "problem", "error", "not working",
        "concerned", "worried", "poor service",
    ],
    weight=0.7,
)

POSITIVE_SENTIMENT_PATTERNS = PatternSet(
    patterns=[
        r"\b(happy|pleased|satisfied|glad)\b",
        r"\b(works?\s+great|working\s+well)\b",
        r"\b(helpful|responsive)\b",
        r"\bappreciate\b",
        r"\bsmooth(ly)?\b",
    ],
    keywords=[
        "happy", "pleased", "satisfied", "works great",
        "helpful", "appreciate", "smooth",
    ],
    weight=0.7,
)

# =============================================================================
# URGENCY PATTERNS
# =============================================================================

HIGH_URGENCY_PATTERNS = PatternSet(
    patterns=[
        r"\b(today|now|immediately|right\s+away)\b",
        r"\bwithin\s+(the\s+)?(hour|1h)\b",
        r"\bCEO|CTO|VP|executive\b",
        r"\bescalat(e|ed|ion)\b",
        r"\bQ[1-4]\s+(deadline|launch|release)\b",
        r"\bend\s+of\s+(day|week|month)\b",
    ],
    keywords=[
        "today", "now", "immediately", "urgent",
        "CEO", "CTO", "escalate", "deadline",
    ],
    weight=1.0,
)

LOW_URGENCY_PATTERNS = PatternSet(
    patterns=[
        r"\bwhen\s+you\s+(have|get)\s+(time|chance)\b",
        r"\bno\s+rush\b",
        r"\bFYI\b",
        r"\bjust\s+(checking|wondering|curious)\b",
        r"\bfor\s+future\s+reference\b",
    ],
    keywords=[
        "no rush", "FYI", "when you have time",
        "just wondering", "future reference",
    ],
    weight=0.5,
)

# =============================================================================
# COMBINED PATTERNS MAP
# =============================================================================

PATTERNS = {
    # Need types
    "urgent_support": URGENT_SUPPORT_PATTERNS,
    "going_dark": GOING_DARK_PATTERNS,
    "frustrated_signal": FRUSTRATED_SIGNAL_PATTERNS,
    "positive_signal": POSITIVE_SIGNAL_PATTERNS,
    "expansion_signal": EXPANSION_SIGNAL_PATTERNS,
    "check_in_due": CHECK_IN_DUE_PATTERNS,
    "stalled_milestone": STALLED_MILESTONE_PATTERNS,
    # Sentiment
    "sentiment_negative": NEGATIVE_SENTIMENT_PATTERNS,
    "sentiment_positive": POSITIVE_SENTIMENT_PATTERNS,
    # Urgency
    "urgency_high": HIGH_URGENCY_PATTERNS,
    "urgency_low": LOW_URGENCY_PATTERNS,
}


def compile_patterns() -> dict[str, list[re.Pattern]]:
    """
    Pre-compile all regex patterns for performance.

    Returns:
        Dict mapping pattern set name to list of compiled regex patterns
    """
    compiled = {}
    for name, pattern_set in PATTERNS.items():
        compiled[name] = [
            re.compile(p, re.IGNORECASE)
            for p in pattern_set.patterns
        ]
    return compiled


# Pre-compiled patterns for performance
COMPILED_PATTERNS = compile_patterns()

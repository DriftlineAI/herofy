"""
Signal Watcher Data Models
Type definitions for signal processing
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4


class SignalSource(str, Enum):
    """Source of an incoming signal."""
    GMAIL = "gmail"
    SLACK = "slack"
    NOTION = "notion"


class Sentiment(str, Enum):
    """Detected sentiment in a signal."""
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    FRUSTRATED = "frustrated"


class Urgency(str, Enum):
    """Signal urgency level."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class MatchType(str, Enum):
    """How a thread match was determined."""
    EXPLICIT = "explicit"  # Reply-to header, Slack thread_ts
    INFERRED = "inferred"  # Subject similarity, timeframe


class CommunicationStyle(str, Enum):
    """Stakeholder communication style."""
    FORMAL = "formal"
    CASUAL = "casual"
    TECHNICAL = "technical"
    BRIEF = "brief"


class EngagementLevel(str, Enum):
    """Stakeholder engagement level."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    DISENGAGED = "disengaged"


class ResponsePattern(str, Enum):
    """Stakeholder response time pattern."""
    FAST = "fast"        # < 1 hour
    NORMAL = "normal"    # 1-4 hours
    SLOW = "slow"        # > 4 hours
    VARIABLE = "variable"


@dataclass
class RawSignal:
    """
    Raw signal fetched from an external source.

    This is the unprocessed signal before classification and matching.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    source: SignalSource = SignalSource.GMAIL
    external_id: str = ""  # Message ID, Slack TS, Notion comment ID

    # Sender info
    sender_email: str | None = None
    sender_name: str = ""
    sender_domain: str | None = None  # For customer matching

    # Content
    subject: str | None = None
    body: str = ""
    channel: str = "email"  # email, slack, meeting, etc.

    # Threading
    reply_to_id: str | None = None  # For explicit thread matching
    thread_id: str | None = None  # External thread reference

    # Metadata
    occurred_at: datetime = field(default_factory=datetime.utcnow)
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Classification:
    """
    Classification result for a signal.

    Produced by a classifier (regex or LLM).
    """
    need_type: str = "uncategorized"
    sentiment: Sentiment = Sentiment.NEUTRAL
    urgency: Urgency = Urgency.MEDIUM
    confidence: float = 0.5  # 0.0 - 1.0
    keywords: list[str] = field(default_factory=list)
    reasoning: str = ""


@dataclass
class ClassifiedSignal(RawSignal):
    """
    Signal after classification.

    Extends RawSignal with classification results and resolved IDs.
    """
    classification: Classification | None = None
    customer_id: str | None = None
    stakeholder_id: str | None = None


@dataclass
class ThreadMatch:
    """
    Result of matching a signal to an existing thread.
    """
    thread_id: str
    match_type: MatchType
    confidence: float  # 0.0 - 1.0
    reason: str = ""
    thread_subject: str | None = None

    @property
    def is_high_confidence(self) -> bool:
        """Check if this is a high-confidence match."""
        return self.match_type == MatchType.EXPLICIT or self.confidence >= 0.8


@dataclass
class NeedMatch:
    """
    Result of matching a signal to an existing need.
    """
    need_id: str
    need_type: str
    confidence: float
    reason: str = ""
    need_headline: str | None = None


@dataclass
class StakeholderProfile:
    """
    Full profile of a stakeholder extracted from signals.
    """
    name: str
    email: str | None = None
    role: str | None = None

    # Sentiment & style
    sentiment: Sentiment = Sentiment.NEUTRAL
    sentiment_note: str = ""  # "Frustrated about deployment delays"
    communication_style: CommunicationStyle = CommunicationStyle.FORMAL

    # Engagement metrics
    response_pattern: ResponsePattern = ResponsePattern.NORMAL
    engagement_level: EngagementLevel = EngagementLevel.MEDIUM

    # Inferred attributes
    timezone_inference: str | None = None  # "PST" based on response times
    is_technical: bool = False
    is_decision_maker: bool = False

    # Tracking
    last_interaction_at: datetime | None = None
    interaction_count: int = 0
    avg_response_hours: float | None = None


@dataclass
class ProcessedSignal:
    """
    Fully processed signal with all matches and enrichment.
    """
    raw_signal: RawSignal
    classification: Classification
    customer_id: str

    # Matching results
    thread_match: ThreadMatch | None = None
    need_match: NeedMatch | None = None

    # Created records (if new)
    created_thread_id: str | None = None
    created_need_id: str | None = None
    created_interaction_id: str | None = None

    # Flags
    is_inferred_match: bool = False  # For UI reassignment
    needs_review: bool = False  # Low confidence


@dataclass
class SignalBatch:
    """
    Batch of signals from a source for processing.
    """
    source: SignalSource
    signals: list[RawSignal] = field(default_factory=list)
    watermark_before: datetime | None = None
    watermark_after: datetime | None = None
    fetch_duration_ms: int | None = None

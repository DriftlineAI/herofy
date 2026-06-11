"""
Signal Classification Models

Pydantic models for LLM classification inputs and outputs.
These provide type-safe validation for all classification data.
"""

from pydantic import BaseModel, Field
from typing import Literal
from uuid import UUID


class SignalClassification(BaseModel):
    """
    Single signal detected in an interaction.

    Maps to the Signal database table.
    """
    kind: Literal["engagement", "sentiment", "commitments"]
    state: Literal["ok", "warn", "risk"]
    sentence: str = Field(
        max_length=200,
        description="One-sentence narrative describing the signal"
    )
    evidence_text: str | None = Field(
        None,
        max_length=500,
        description="Direct quote from the interaction as evidence"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0-1.0)"
    )
    reasoning: str | None = Field(
        None,
        description="Why this signal was detected"
    )


class CommitmentExtraction(BaseModel):
    """
    Commitment extracted from conversation.

    Represents explicit promises or deadlines made by either party.
    """
    what: str = Field(description="What was promised or committed to")
    who: Literal["us", "them"] = Field(
        description="Who made the commitment (us=CSM, them=customer)"
    )
    due_date: str | None = Field(
        None,
        description="Due date if mentioned (ISO format: YYYY-MM-DD)"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in the extraction"
    )


class ContentClassificationOutput(BaseModel):
    """
    Complete LLM response for content classification.

    Contains all signals, commitments, and suggested need type.
    """
    signals: list[SignalClassification] = Field(
        default_factory=list,
        description="Health signals detected (typically 0-3)"
    )
    commitments: list[CommitmentExtraction] = Field(
        default_factory=list,
        description="Explicit commitments made"
    )
    suggested_need_type: str | None = Field(
        None,
        description="Suggested need type if action is required"
    )
    overall_confidence: float = Field(
        ge=0.0,
        le=1.0,
        default=0.0,
        description="Overall confidence in the classification"
    )
    extraction_notes: str | None = Field(
        None,
        description="Additional notes from the LLM"
    )


class SignalWithNeed(BaseModel):
    """
    Result of signal processing: Signal + optional auto-generated Need.

    Returned from SignalClassificationService.classify_and_process().
    """
    signal_id: UUID
    need_id: UUID | None = None
    need_type: str | None = None
    confidence: float
    signal_kind: str = ""   # 'engagement' | 'sentiment' | 'commitments' | 'going_dark' | 'cadence'
    signal_state: str = ""  # 'ok' | 'warn' | 'risk'
    signal_sentence: str = ""

    class Config:
        """Pydantic configuration."""
        frozen = True  # Immutable after creation

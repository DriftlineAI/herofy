"""
Pydantic validation models for Customer Enrichment AI output.

These models validate the structure of LLM-generated JSON responses
to ensure they match expected schemas before writing to the database.

The AI extraction principle: "Extract what's stated, don't infer what isn't."
- Only extract stakeholders, goals, signals if explicitly mentioned in notes
- Don't manufacture sentiment or risk stories where none exist
- Leave fields null/empty if no evidence in source data
"""

from typing import Literal

from pydantic import BaseModel, Field


class StakeholderData(BaseModel):
    """
    Extracted stakeholder from CRM notes.

    Only populated if a person is explicitly mentioned with context.
    """
    name: str
    email: str | None = None
    role: str | None = None
    sentiment_note: str | None = None  # Only if sentiment is explicitly described

    class Config:
        extra = "allow"


class GoalData(BaseModel):
    """
    Extracted business goal from CRM notes.

    Only populated if an explicit goal/outcome is stated.
    Goals should be outcome-focused, not activity-focused.
    """
    text: str
    status: Literal["active", "achieved", "dropped"] = "active"
    priority: Literal["primary", "secondary", "exploratory"] = "secondary"
    success_criteria: str | None = None  # How success would be measured

    class Config:
        extra = "allow"


class SignalData(BaseModel):
    """
    Extracted health signal from CRM notes.

    Only populated if the notes explicitly describe:
    - Sentiment: e.g., "frustrated", "excited", "concerned"
    - Commitments: e.g., "promised to deliver X by Y"

    Do NOT infer engagement signals from static documents.
    """
    kind: Literal["sentiment", "commitments"]  # No "engagement" - can't infer from static docs
    state: Literal["ok", "warn", "risk"]
    sentence: str  # One-sentence narrative describing what's stated
    evidence_text: str | None = None  # Quote or reference from notes

    class Config:
        extra = "allow"


class EnrichmentOutput(BaseModel):
    """
    Complete enrichment output from a single LLM call.

    All fields are optional - only populate what's explicitly stated in the notes.
    The AI must not invent information that isn't present.
    """
    # Summary - always attempt to generate
    one_liner: str | None = Field(
        default=None,
        description="A single sentence describing what this customer does (max 120 chars)"
    )

    # Extracted entities - only if explicitly mentioned
    stakeholders: list[StakeholderData] = Field(
        default_factory=list,
        description="People mentioned in the notes with their roles/context"
    )
    goals: list[GoalData] = Field(
        default_factory=list,
        description="Business goals or desired outcomes explicitly stated"
    )
    signals: list[SignalData] = Field(
        default_factory=list,
        description="Sentiment or commitment signals explicitly described (not inferred)"
    )

    # Risk context - only if notes describe a risk situation
    risk_brief: str | None = Field(
        default=None,
        description="2-3 sentence risk summary. Only if notes describe actual risk/concern."
    )

    # Extraction metadata
    extraction_notes: str | None = Field(
        default=None,
        description="Any notes about what could/couldn't be extracted"
    )

    class Config:
        extra = "allow"  # Allow extra fields from LLM


class EnrichmentInput(BaseModel):
    """
    Input data for enrichment processing.
    """
    customer_id: str
    customer_name: str
    raw_notes: str
    linked_pages_content: str | None = None  # Combined content from linked pages (Notion, etc.)
    existing_tier: str | None = None
    existing_arr_cents: int | None = None
    existing_lifecycle: str | None = None

    class Config:
        extra = "allow"

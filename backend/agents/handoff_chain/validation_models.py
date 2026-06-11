"""
Pydantic validation models for HandoffChain step outputs.

These models validate the structure of LLM-generated JSON responses
to ensure they match expected schemas before processing.

Example:
    from core.validation import validate_output
    from .validation_models import GapAnalysisOutput

    @validate_output(GapAnalysisOutput, extract_field="gap_analysis")
    async def gap_analysis_step(ctx, llm_model):
        ...
"""

from typing import Literal

from pydantic import BaseModel, Field


class GapAnalysisOutput(BaseModel):
    """
    Validation model for gap_analysis_step output.

    Validates the JSON structure from the LLM gap analysis.
    """

    confidence: Literal["low", "medium", "high"] = "medium"
    timeline_feasible: bool = True
    risks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    needs_clarification: bool = False

    class Config:
        extra = "allow"  # Allow extra fields from LLM


class PlanMilestone(BaseModel):
    """
    Validation model for a single milestone in the plan.
    """

    title: str
    description: str = ""
    owner_side: Literal["vendor", "customer", "joint"] = "joint"
    duration_days: int = Field(default=7, ge=1, le=365)
    dependencies: list[str] = Field(default_factory=list)


class PlanGenerationOutput(BaseModel):
    """
    Validation model for generate_plan_step output.

    Validates the JSON structure from the LLM plan generation.
    """

    headline: str = "Onboarding plan generated"
    rationale: str = ""
    milestones: list[PlanMilestone] = Field(default_factory=list)
    total_duration_days: int | None = None
    warnings: list[str] = Field(default_factory=list)

    class Config:
        extra = "allow"  # Allow extra fields from LLM


class DealDataInput(BaseModel):
    """
    Validation model for deal data from Notion.

    Ensures required fields are present before processing.
    """

    company_name: str
    arr_cents: int = 0
    timeline: str | None = None
    stakeholders: list[dict] = Field(default_factory=list)
    sales_commitments: list[dict] = Field(default_factory=list)
    technical_context: list[dict] = Field(default_factory=list)

    class Config:
        extra = "allow"  # Allow extra fields from Notion


class PlaybookMilestone(BaseModel):
    """
    Validation model for a playbook milestone.
    """

    title: str
    description: str = ""
    owner_side: Literal["vendor", "customer", "joint"] = "joint"
    duration_days: int = 7
    order_index: int = 0


class PlaybookInput(BaseModel):
    """
    Validation model for playbook data from database.
    """

    id: str
    name: str
    archetype: str = "standard"
    description: str = ""
    expected_duration_days: int = 45

    class Config:
        extra = "allow"

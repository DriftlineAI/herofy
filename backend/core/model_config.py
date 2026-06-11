"""
Model Configuration

Centralizes model selection for different use cases.
Allows easy switching between models for different tasks.
"""

from enum import Enum


class ModelUseCase(str, Enum):
    """Use cases for model selection."""

    # Agent operations
    PLAN_GENERATION = "plan_generation"
    HANDOFF_BRIEF = "handoff_brief"
    SIGNAL_ANALYSIS = "signal_analysis"
    GAP_ANALYSIS = "gap_analysis"

    # Draft generation
    DRAFT_EMAIL = "draft_email"
    DRAFT_SLACK = "draft_slack"

    # Analysis
    SENTIMENT_ANALYSIS = "sentiment_analysis"
    ENTITY_EXTRACTION = "entity_extraction"
    SIGNAL_CLASSIFICATION = "signal_classification"

    # Enrichment (customer data extraction from CRM notes)
    ENRICHMENT = "enrichment"

    # Playbook generation from natural language
    PLAYBOOK_GENERATION = "playbook_generation"


# Model mappings by use case
# gemini-2.5-flash: Complex reasoning, synthesis, creative writing
# gemini-2.5-flash-lite: Simple classification, structured extraction (cheaper, faster)
MODEL_CONFIG: dict[ModelUseCase, str] = {
    # Complex reasoning tasks - need full model
    ModelUseCase.PLAN_GENERATION: "gemini-2.5-flash",
    ModelUseCase.HANDOFF_BRIEF: "gemini-2.5-flash",
    ModelUseCase.SIGNAL_ANALYSIS: "gemini-2.5-flash",
    ModelUseCase.GAP_ANALYSIS: "gemini-2.5-flash",
    ModelUseCase.DRAFT_EMAIL: "gemini-2.5-flash",
    ModelUseCase.DRAFT_SLACK: "gemini-2.5-flash",
    ModelUseCase.ENRICHMENT: "gemini-2.5-flash",
    ModelUseCase.PLAYBOOK_GENERATION: "gemini-2.5-flash",
    # Simple classification tasks - use lite model (cheaper, faster)
    ModelUseCase.SENTIMENT_ANALYSIS: "gemini-2.5-flash-lite",
    ModelUseCase.ENTITY_EXTRACTION: "gemini-2.5-flash-lite",
    ModelUseCase.SIGNAL_CLASSIFICATION: "gemini-2.5-flash-lite",
}

# Default model for any use case not explicitly mapped
DEFAULT_MODEL = "gemini-2.5-flash"


def get_model(use_case: ModelUseCase, tier: str | None = None) -> str:
    """
    Get the model identifier for a specific use case.

    Args:
        use_case: The ModelUseCase enum value
        tier: Optional customer tier (reserved for future tier-based model selection)

    Returns:
        Model identifier string (e.g., "gemini-2.5-flash")
    """
    # TODO: Use tier for differentiated model selection (e.g., pro tier gets better models)
    return MODEL_CONFIG.get(use_case, DEFAULT_MODEL)

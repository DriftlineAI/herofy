"""
Signal Classification Service

LLM-based classification of customer interactions to detect health signals
and auto-create Needs in the Today Queue.

Usage:
    from services.signal_classification import SignalClassificationService

    service = SignalClassificationService(workspace_id=workspace_id)
    results = await service.classify_and_process(event, customer_id)
"""

from .service import SignalClassificationService
from .models import (
    SignalClassification,
    CommitmentExtraction,
    ContentClassificationOutput,
    SignalWithNeed,
)
from .llm_classifier import LLMSignalClassifier
from .signal_to_need_mapper import SignalToNeedMapper

__all__ = [
    "SignalClassificationService",
    "LLMSignalClassifier",
    "SignalToNeedMapper",
    "SignalClassification",
    "CommitmentExtraction",
    "ContentClassificationOutput",
    "SignalWithNeed",
]

"""
Signal Classifier Base
Abstract interface for signal classifiers
"""

from abc import ABC, abstractmethod

from ..models import RawSignal, Classification


class SignalClassifierBase(ABC):
    """
    Abstract base class for signal classifiers.

    Implementations must provide:
    - classify(): Determine need_type, sentiment, urgency from signal content

    The classifier can be:
    - RegexClassifier: Fast keyword matching (default)
    - HybridClassifier: Regex + LLM fallback for ambiguous cases
    - LLMClassifier: Full LLM classification (expensive, accurate)
    """

    @abstractmethod
    def classify(self, signal: RawSignal) -> Classification:
        """
        Classify a signal to determine its need_type, sentiment, and urgency.

        Args:
            signal: The raw signal to classify

        Returns:
            Classification with need_type, sentiment, urgency, and confidence
        """
        pass

    @abstractmethod
    async def classify_async(self, signal: RawSignal) -> Classification:
        """
        Async version of classify for LLM-based classifiers.

        Args:
            signal: The raw signal to classify

        Returns:
            Classification result
        """
        pass

    def classify_batch(self, signals: list[RawSignal]) -> list[Classification]:
        """
        Classify multiple signals.

        Default implementation calls classify() for each signal.
        Override for batch-optimized implementations.

        Args:
            signals: List of raw signals

        Returns:
            List of classifications in the same order
        """
        return [self.classify(signal) for signal in signals]

    def _extract_text(self, signal: RawSignal) -> str:
        """
        Extract full text content from a signal for classification.

        Combines subject and body for analysis.
        """
        parts = []
        if signal.subject:
            parts.append(signal.subject)
        if signal.body:
            parts.append(signal.body)
        return " ".join(parts)

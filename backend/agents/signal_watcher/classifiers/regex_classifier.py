"""
Regex-Based Signal Classifier
Fast keyword and pattern matching for signal classification

Design notes:
- Uses pre-compiled regex patterns for performance
- Falls back to keyword matching for fuzzy scenarios
- Designed for easy upgrade path to LLM hybrid
- Returns confidence scores based on match strength
"""

import re
from typing import Any

from core.logging import get_logger
from ..models import RawSignal, Classification, Sentiment, Urgency
from .base import SignalClassifierBase
from .patterns import PATTERNS, COMPILED_PATTERNS, PatternSet

logger = get_logger("RegexClassifier")


class RegexClassifier(SignalClassifierBase):
    """
    Regex-based signal classifier.

    Uses pattern matching and keyword detection to classify signals.
    Fast and deterministic, suitable for high-volume processing.
    """

    def __init__(self, use_fuzzy: bool = True):
        """
        Initialize the classifier.

        Args:
            use_fuzzy: Enable fuzzy keyword matching (slightly slower, more accurate)
        """
        self.use_fuzzy = use_fuzzy

    def classify(self, signal: RawSignal) -> Classification:
        """
        Classify a signal synchronously using regex patterns.

        Args:
            signal: The raw signal to classify

        Returns:
            Classification with need_type, sentiment, urgency, and confidence
        """
        text = self._extract_text(signal)
        text_lower = text.lower()

        # Score each need type
        need_scores = self._score_need_types(text, text_lower)

        # Determine best need type
        need_type, need_confidence = self._select_best_match(need_scores)

        # Score sentiment
        sentiment, sentiment_confidence = self._classify_sentiment(text, text_lower)

        # Score urgency
        urgency, urgency_confidence = self._classify_urgency(text, text_lower)

        # Extract keywords found
        keywords = self._extract_matched_keywords(text_lower, need_type)

        # Build reasoning
        reasoning = self._build_reasoning(need_type, sentiment, urgency, keywords)

        # Calculate overall confidence
        confidence = self._calculate_confidence(
            need_confidence, sentiment_confidence, urgency_confidence
        )

        classification = Classification(
            need_type=need_type,
            sentiment=sentiment,
            urgency=urgency,
            confidence=confidence,
            keywords=keywords,
            reasoning=reasoning,
        )

        logger.debug(
            "signal_classified",
            need_type=need_type,
            sentiment=sentiment.value,
            urgency=urgency.value,
            confidence=confidence,
        )

        return classification

    async def classify_async(self, signal: RawSignal) -> Classification:
        """Async wrapper for sync classify (regex is fast, no async needed)."""
        return self.classify(signal)

    def _score_need_types(self, text: str, text_lower: str) -> dict[str, float]:
        """
        Score each need type based on pattern matches.

        Returns:
            Dict mapping need_type to confidence score (0-1)
        """
        scores = {}

        need_type_keys = [
            "urgent_support",
            "going_dark",
            "frustrated_signal",
            "positive_signal",
            "expansion_signal",
            "check_in_due",
            "stalled_milestone",
        ]

        for key in need_type_keys:
            pattern_set = PATTERNS.get(key)
            compiled = COMPILED_PATTERNS.get(key, [])

            if not pattern_set:
                continue

            score = 0.0
            matches = 0

            # Check regex patterns
            for pattern in compiled:
                if pattern.search(text):
                    matches += 1
                    score += 0.3  # Each pattern match adds confidence

            # Check keywords (fuzzy if enabled)
            for keyword in pattern_set.keywords:
                if self.use_fuzzy:
                    if self._fuzzy_keyword_match(keyword, text_lower):
                        matches += 1
                        score += 0.2
                else:
                    if keyword.lower() in text_lower:
                        matches += 1
                        score += 0.2

            # Apply weight
            if matches > 0:
                scores[key] = min(1.0, score * pattern_set.weight)

        return scores

    def _select_best_match(self, scores: dict[str, float]) -> tuple[str, float]:
        """
        Select the best matching need type.

        Returns:
            Tuple of (need_type, confidence)
        """
        if not scores:
            return "uncategorized", 0.3

        # Sort by score descending
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        best_type, best_score = sorted_scores[0]

        # If multiple high scorers, reduce confidence
        if len(sorted_scores) > 1 and sorted_scores[1][1] > 0.5:
            # Competing matches reduce confidence
            best_score *= 0.8

        return best_type, best_score

    def _classify_sentiment(self, text: str, text_lower: str) -> tuple[Sentiment, float]:
        """
        Classify sentiment from text.

        Returns:
            Tuple of (Sentiment, confidence)
        """
        positive_score = 0.0
        negative_score = 0.0

        # Check frustrated patterns (strong negative)
        frustrated_patterns = COMPILED_PATTERNS.get("frustrated_signal", [])
        for pattern in frustrated_patterns:
            if pattern.search(text):
                return Sentiment.FRUSTRATED, 0.9

        # Check positive patterns
        positive_patterns = COMPILED_PATTERNS.get("sentiment_positive", [])
        for pattern in positive_patterns:
            if pattern.search(text):
                positive_score += 0.3

        # Check negative patterns
        negative_patterns = COMPILED_PATTERNS.get("sentiment_negative", [])
        for pattern in negative_patterns:
            if pattern.search(text):
                negative_score += 0.3

        # Determine sentiment
        if positive_score > negative_score and positive_score > 0.2:
            return Sentiment.POSITIVE, min(1.0, positive_score)
        elif negative_score > positive_score and negative_score > 0.2:
            return Sentiment.NEGATIVE, min(1.0, negative_score)
        else:
            return Sentiment.NEUTRAL, 0.5

    def _classify_urgency(self, text: str, text_lower: str) -> tuple[Urgency, float]:
        """
        Classify urgency level.

        Returns:
            Tuple of (Urgency, confidence)
        """
        high_score = 0.0
        low_score = 0.0

        # Check high urgency patterns
        high_patterns = COMPILED_PATTERNS.get("urgency_high", [])
        for pattern in high_patterns:
            if pattern.search(text):
                high_score += 0.4

        # Check low urgency patterns
        low_patterns = COMPILED_PATTERNS.get("urgency_low", [])
        for pattern in low_patterns:
            if pattern.search(text):
                low_score += 0.3

        # Also check urgent need types
        urgent_patterns = COMPILED_PATTERNS.get("urgent_support", [])
        for pattern in urgent_patterns:
            if pattern.search(text):
                high_score += 0.3
                break

        # Determine urgency
        if high_score > 0.5:
            return Urgency.URGENT, min(1.0, high_score)
        elif high_score > 0.2:
            return Urgency.HIGH, min(1.0, high_score)
        elif low_score > 0.2:
            return Urgency.LOW, min(1.0, low_score)
        else:
            return Urgency.MEDIUM, 0.5

    def _fuzzy_keyword_match(self, keyword: str, text_lower: str) -> bool:
        """
        Fuzzy match a keyword in text.

        Handles common variations:
        - Word boundaries
        - Partial matches (3+ char words)
        - Hyphenation variants
        """
        keyword_lower = keyword.lower()

        # Direct match
        if keyword_lower in text_lower:
            return True

        # Try word boundary match
        pattern = r"\b" + re.escape(keyword_lower) + r"\b"
        if re.search(pattern, text_lower):
            return True

        # Try hyphen/space variants
        keyword_variants = [
            keyword_lower.replace("-", " "),
            keyword_lower.replace(" ", "-"),
            keyword_lower.replace(" ", ""),
        ]
        for variant in keyword_variants:
            if variant in text_lower:
                return True

        return False

    def _extract_matched_keywords(self, text_lower: str, need_type: str) -> list[str]:
        """
        Extract keywords that matched for the given need type.

        Returns:
            List of matched keywords
        """
        matched = []
        pattern_set = PATTERNS.get(need_type)

        if pattern_set:
            for keyword in pattern_set.keywords:
                if keyword.lower() in text_lower:
                    matched.append(keyword)

        return matched[:5]  # Limit to top 5

    def _build_reasoning(
        self,
        need_type: str,
        sentiment: Sentiment,
        urgency: Urgency,
        keywords: list[str],
    ) -> str:
        """
        Build human-readable reasoning for the classification.
        """
        parts = []

        # Need type reasoning
        need_type_display = need_type.replace("_", " ").title()
        parts.append(f"Classified as '{need_type_display}'")

        if keywords:
            parts.append(f"based on keywords: {', '.join(keywords)}")

        # Sentiment
        parts.append(f"Sentiment: {sentiment.value}")

        # Urgency
        parts.append(f"Urgency: {urgency.value}")

        return ". ".join(parts) + "."

    def _calculate_confidence(
        self,
        need_confidence: float,
        sentiment_confidence: float,
        urgency_confidence: float,
    ) -> float:
        """
        Calculate overall classification confidence.

        Weighted average with need_type being most important.
        """
        return (
            need_confidence * 0.5 +
            sentiment_confidence * 0.25 +
            urgency_confidence * 0.25
        )

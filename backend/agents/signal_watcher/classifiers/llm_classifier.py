"""
LLM-based Signal Classifier.

Uses Gemini to classify signals when regex confidence is low.
Designed as fallback for the HybridClassifier.

Example:
    classifier = LLMClassifier()
    classification = await classifier.classify_async(signal)
"""

import json
from typing import Any

from google import genai

from core.logging import get_logger
from core.retry import retry_with_backoff
from core.model_config import get_model, ModelUseCase

from ..models import RawSignal, Classification, Sentiment, Urgency
from .base import SignalClassifierBase

logger = get_logger("LLMClassifier")

# LLM classification prompt
CLASSIFICATION_PROMPT = """You are a Customer Success AI assistant analyzing customer signals.

Classify this customer communication:

From: {sender_name} ({sender_email})
Subject: {subject}
Body:
{body}

Determine:
1. need_type: The type of customer need this represents
2. sentiment: The emotional tone of the message
3. urgency: How urgent this requires attention
4. confidence: How confident you are in this classification (0.0-1.0)
5. keywords: Key words that informed the classification
6. reasoning: Brief explanation of your classification

Valid need_types:
- urgent_support: Customer needs immediate help with a critical issue
- going_dark: Customer has stopped responding or engaging
- frustrated_signal: Customer expressing frustration or dissatisfaction
- positive_signal: Customer expressing satisfaction or praise
- expansion_signal: Customer interested in upgrading or expanding
- check_in_due: Routine check-in needed
- stalled_milestone: Progress on onboarding/project has stalled
- approaching_renewal: Renewal date approaching, needs attention
- champion_departed: Key contact leaving the company
- uncategorized: Does not fit other categories

Valid sentiment values: positive, neutral, negative, frustrated
Valid urgency values: low, medium, high, urgent

Respond with ONLY valid JSON (no markdown, no explanation):
{{
    "need_type": "...",
    "sentiment": "...",
    "urgency": "...",
    "confidence": 0.85,
    "keywords": ["keyword1", "keyword2"],
    "reasoning": "Brief explanation"
}}"""


class LLMClassifier(SignalClassifierBase):
    """
    LLM-based signal classifier using Gemini.

    More accurate than regex but slower and more expensive.
    Use as fallback for low-confidence regex classifications.
    """

    def __init__(self, model_name: str | None = None):
        """
        Initialize the classifier.

        Args:
            model_name: Gemini model to use (default: from model config)
        """
        self.model_name = model_name or get_model(ModelUseCase.SIGNAL_CLASSIFICATION)
        self._client: genai.Client | None = None

    def _get_client(self) -> genai.Client:
        """Lazy initialize the GenAI client."""
        if self._client is None:
            from config import settings

            if not settings.gemini_api_key:
                raise ValueError("GEMINI_API_KEY not configured")

            self._client = genai.Client(api_key=settings.gemini_api_key)

        return self._client

    def classify(self, signal: RawSignal) -> Classification:
        """
        Synchronous classification (runs async in background).

        For true sync classification, use regex classifier.
        """
        import asyncio

        return asyncio.run(self.classify_async(signal))

    @retry_with_backoff(max_attempts=3, base_delay=1.0, max_delay=10.0)
    async def classify_async(self, signal: RawSignal) -> Classification:
        """
        Classify signal using LLM.

        Args:
            signal: The raw signal to classify

        Returns:
            Classification with need_type, sentiment, urgency, and confidence
        """
        client = self._get_client()

        # Build prompt
        prompt = self._build_prompt(signal)

        logger.debug(
            "llm_classification_started",
            signal_id=signal.id,
            model=self.model_name,
        )

        try:
            # Call LLM
            response = await client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            response_text = response.text.strip()

            # Parse JSON response
            classification_data = self._parse_response(response_text)

            classification = Classification(
                need_type=classification_data.get("need_type", "uncategorized"),
                sentiment=self._parse_sentiment(classification_data.get("sentiment", "neutral")),
                urgency=self._parse_urgency(classification_data.get("urgency", "medium")),
                confidence=float(classification_data.get("confidence", 0.8)),
                keywords=classification_data.get("keywords", []),
                reasoning=classification_data.get("reasoning", "Classified by LLM"),
            )

            logger.info(
                "llm_classification_completed",
                signal_id=signal.id,
                need_type=classification.need_type,
                sentiment=classification.sentiment.value,
                confidence=classification.confidence,
            )

            return classification

        except json.JSONDecodeError as e:
            logger.error(
                "llm_response_parse_error",
                signal_id=signal.id,
                error=str(e),
            )
            # Return low-confidence fallback
            return Classification(
                need_type="uncategorized",
                sentiment=Sentiment.NEUTRAL,
                urgency=Urgency.MEDIUM,
                confidence=0.3,
                reasoning="LLM response parsing failed",
            )

        except Exception as e:
            logger.error(
                "llm_classification_failed",
                signal_id=signal.id,
                error=str(e),
            )
            raise

    def _build_prompt(self, signal: RawSignal) -> str:
        """Build the classification prompt."""
        # Truncate body to avoid token limits
        body = signal.body[:2000] if signal.body else "(empty)"

        return CLASSIFICATION_PROMPT.format(
            sender_name=signal.sender_name or "Unknown",
            sender_email=signal.sender_email or "unknown@example.com",
            subject=signal.subject or "(no subject)",
            body=body,
        )

    def _parse_response(self, response_text: str) -> dict[str, Any]:
        """Parse JSON from LLM response, handling various formats."""
        text = response_text.strip()

        # Try direct JSON parse
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        # Try extracting from markdown code block
        import re

        code_block_pattern = r"```(?:json)?\s*\n?([\s\S]*?)\n?```"
        matches = re.findall(code_block_pattern, text)
        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue

        # Try finding JSON object in text
        json_pattern = r"\{[\s\S]*\}"
        json_matches = re.findall(json_pattern, text)
        for match in json_matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

        # Nothing worked
        raise json.JSONDecodeError("No valid JSON found", text, 0)

    def _parse_sentiment(self, value: str) -> Sentiment:
        """Parse sentiment string to enum."""
        mapping = {
            "positive": Sentiment.POSITIVE,
            "neutral": Sentiment.NEUTRAL,
            "negative": Sentiment.NEGATIVE,
            "frustrated": Sentiment.FRUSTRATED,
        }
        return mapping.get(value.lower(), Sentiment.NEUTRAL)

    def _parse_urgency(self, value: str) -> Urgency:
        """Parse urgency string to enum."""
        mapping = {
            "low": Urgency.LOW,
            "medium": Urgency.MEDIUM,
            "high": Urgency.HIGH,
            "urgent": Urgency.URGENT,
        }
        return mapping.get(value.lower(), Urgency.MEDIUM)


class HybridClassifier(SignalClassifierBase):
    """
    Hybrid classifier: regex first, LLM fallback for low confidence.

    Uses regex for fast classification, falls back to LLM when:
    - Classification mode is "always_llm"
    - Regex confidence is below threshold

    Configuration via settings:
    - signal_classification_mode: "always_llm" | "threshold"
    - signal_llm_confidence_threshold: 0.5 (default)
    """

    def __init__(self, use_fuzzy: bool = True):
        """
        Initialize the hybrid classifier.

        Args:
            use_fuzzy: Enable fuzzy keyword matching in regex classifier
        """
        from .regex_classifier import RegexClassifier

        self.regex_classifier = RegexClassifier(use_fuzzy=use_fuzzy)
        self._llm_classifier: LLMClassifier | None = None

    def _get_llm_classifier(self) -> LLMClassifier:
        """Lazy initialize LLM classifier."""
        if self._llm_classifier is None:
            self._llm_classifier = LLMClassifier()
        return self._llm_classifier

    def classify(self, signal: RawSignal) -> Classification:
        """
        Synchronous classification using regex only.

        For LLM fallback, use classify_async.
        """
        return self.regex_classifier.classify(signal)

    async def classify_async(self, signal: RawSignal) -> Classification:
        """
        Classify signal with LLM fallback for low confidence.

        Args:
            signal: The raw signal to classify

        Returns:
            Classification result
        """
        from config import settings

        # Get classification mode from settings
        mode = getattr(settings, "signal_classification_mode", "threshold")
        threshold = getattr(settings, "signal_llm_confidence_threshold", 0.5)

        # Always LLM mode
        if mode == "always_llm":
            logger.debug(
                "classification_always_llm",
                signal_id=signal.id,
            )
            return await self._get_llm_classifier().classify_async(signal)

        # Threshold mode: try regex first
        regex_result = self.regex_classifier.classify(signal)

        # Check if we should escalate to LLM
        if regex_result.confidence < threshold:
            logger.info(
                "classification_escalating_to_llm",
                signal_id=signal.id,
                regex_confidence=regex_result.confidence,
                threshold=threshold,
            )
            return await self._get_llm_classifier().classify_async(signal)

        # Regex confidence is acceptable
        logger.debug(
            "classification_regex_sufficient",
            signal_id=signal.id,
            confidence=regex_result.confidence,
        )
        return regex_result

"""
LLM Signal Classifier

Gemini-based classification of unstructured content for health signals.
Uses Gemini 2.5 Flash for fast, cost-effective classification.
"""

import json
import re
from typing import Any

from google import genai

from config import get_settings
from core.retry import retry_with_backoff
from core.logging import get_logger
from core.events import ChangeEvent
from core.model_config import get_model, ModelUseCase

from .models import ContentClassificationOutput, SignalClassification, CommitmentExtraction

logger = get_logger("LLMSignalClassifier")

# =============================================================================
# LLM Prompt Template
# =============================================================================

CLASSIFICATION_PROMPT = """You are a Customer Success AI analyzing customer interactions for health signals.

**INTERACTION:**
From: {sender_name} ({sender_email})
Channel: {channel}
Subject: {subject}
Body:
{body}

**CUSTOMER CONTEXT:**
Customer: {customer_name}
Lifecycle: {lifecycle}
Tier: {tier}
Recent Signals: {recent_summary}

**TASK:** Analyze this interaction and detect health signals.

**SIGNAL TYPES:**
1. **engagement** - Activity and responsiveness patterns
   - ok: Active, timely responses, engaged
   - warn: Slower responses, less engaged than usual
   - risk: Gone dark, stopped responding

2. **sentiment** - Emotional tone and satisfaction
   - ok: Positive, happy, satisfied
   - warn: Concerns raised, minor frustration
   - risk: Frustrated, angry, escalating

3. **commitments** - Promises and deadlines
   - ok: Commitments being kept, on track
   - warn: Deadlines approaching, follow-up needed
   - risk: Overdue commitments, broken promises

**NEED TYPES (only suggest if action required):**
- urgent_support: Critical issue blocking customer
- frustrated_signal: Customer expressing frustration/dissatisfaction
- positive_signal: Praise, success, or satisfaction worth noting
- expansion_signal: Interest in upgrading, adding users, or new features
- champion_departed: Key contact leaving the company
- going_dark: Customer stopped responding (engagement risk)
- check_in_due: Routine follow-up needed
- open_commitment_overdue: A promise (ours or theirs) is past due
- uncategorized: Needs attention but doesn't fit categories

**GUIDELINES:**
- Only extract signals with clear evidence in the text
- Confidence > 0.7 should trigger automatic Need creation
- Confidence 0.5-0.7 creates Signal without Need (for tracking)
- Confidence < 0.5 means routine/no action
- Max 3 signals per interaction (focus on most important)
- Extract specific commitments with who/what/when
- **IMPORTANT:** For commitments, "who" must be ONLY "us" (your team/CSM) or "them" (the customer), NOT a person's name
- Be conservative: routine emails should return low confidence

**RESPOND WITH JSON ONLY (no markdown):**
{{
  "signals": [
    {{
      "kind": "sentiment",
      "state": "warn",
      "sentence": "Customer expressed frustration about deployment timeline",
      "evidence_text": "We're really frustrated that this is taking so long...",
      "confidence": 0.85,
      "reasoning": "Explicit frustration language about delays"
    }}
  ],
  "commitments": [
    {{
      "what": "Schedule deployment call with engineering",
      "who": "us",
      "due_date": "2026-05-25",
      "confidence": 0.9
    }}
  ],
  "suggested_need_type": "frustrated_signal",
  "overall_confidence": 0.85,
  "extraction_notes": "Clear frustration with timeline expectations"
}}"""


class LLMSignalClassifier:
    """
    Gemini-based signal classifier for unstructured content.

    Uses Gemini 2.5 Flash for fast, cost-effective classification.
    Includes retry logic and graceful degradation.
    """

    def __init__(self, model_name: str | None = None):
        """
        Initialize classifier.

        Args:
            model_name: Gemini model to use (default: from model config)
        """
        self.model_name = model_name or get_model(ModelUseCase.SIGNAL_CLASSIFICATION)
        self._client: genai.Client | None = None

    def _get_client(self) -> genai.Client:
        """
        Lazy initialize GenAI client.

        Returns:
            Initialized Gemini client
        """
        if self._client is None:
            settings = get_settings()
            if not settings.gemini_api_key:
                raise ValueError("GEMINI_API_KEY not configured")
            self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client

    @retry_with_backoff(max_attempts=3, base_delay=1.0, max_delay=10.0)
    async def classify_content(
        self,
        event: ChangeEvent,
        customer_context: dict[str, Any],
    ) -> ContentClassificationOutput:
        """
        Classify ChangeEvent content for signals and commitments.

        Args:
            event: The ChangeEvent to classify
            customer_context: Customer data (name, lifecycle, recent signals)

        Returns:
            ContentClassificationOutput with signals, commitments, suggested need
        """
        client = self._get_client()
        prompt = self._build_prompt(event, customer_context)

        logger.debug(
            "llm_classification_started",
            event_id=str(event.id),
            source=event.source.value,
            model=self.model_name,
        )

        try:
            response = await client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            response_text = response.text.strip()

            # Parse and validate JSON
            raw_output = self._extract_json(response_text)
            output = self._parse_output(raw_output)

            logger.info(
                "llm_classification_completed",
                event_id=str(event.id),
                signals_count=len(output.signals),
                commitments_count=len(output.commitments),
                confidence=output.overall_confidence,
                suggested_need=output.suggested_need_type,
            )

            return output

        except json.JSONDecodeError as e:
            logger.error(
                "llm_response_parse_error",
                event_id=str(event.id),
                error=str(e),
            )
            # Return safe fallback
            return ContentClassificationOutput(
                signals=[],
                commitments=[],
                overall_confidence=0.0,
                extraction_notes=f"Parse error: {e}",
            )

        except Exception as e:
            logger.error(
                "llm_classification_failed",
                event_id=str(event.id),
                error=str(e),
            )
            # Return safe fallback
            return ContentClassificationOutput(
                signals=[],
                commitments=[],
                overall_confidence=0.0,
                extraction_notes=f"Classification failed: {e}",
            )

    def _build_prompt(
        self,
        event: ChangeEvent,
        customer_context: dict[str, Any],
    ) -> str:
        """
        Build classification prompt with context.

        Args:
            event: ChangeEvent to classify
            customer_context: Customer data

        Returns:
            Formatted prompt string
        """
        payload = event.raw_payload

        # Extract interaction details
        sender_name = payload.get("sender_name", "Unknown")
        sender_email = payload.get("sender_email", "")
        subject = payload.get("subject", "(no subject)")
        body = payload.get("body", "")[:2000]  # Truncate long bodies
        channel = payload.get("channel", event.source.value)

        # Customer context
        customer_name = customer_context.get("name", "Unknown")
        lifecycle = customer_context.get("lifecycle", "unknown")
        tier = customer_context.get("tier", "unknown")
        recent_summary = self._build_recent_summary(customer_context)

        return CLASSIFICATION_PROMPT.format(
            sender_name=sender_name,
            sender_email=sender_email,
            channel=channel,
            subject=subject,
            body=body,
            customer_name=customer_name,
            lifecycle=lifecycle,
            tier=tier,
            recent_summary=recent_summary,
        )

    def _build_recent_summary(self, customer_context: dict[str, Any]) -> str:
        """
        Build recent activity summary for context.

        Args:
            customer_context: Customer data with recent_signals

        Returns:
            Formatted summary string
        """
        recent_signals = customer_context.get("recent_signals", [])
        if not recent_signals:
            return "No recent signals"

        summary_parts = []
        for sig in recent_signals[:3]:
            kind = sig.get("kind", "unknown")
            state = sig.get("state", "unknown")
            sentence = sig.get("sentence", "Unknown signal")
            summary_parts.append(f"- {kind}/{state}: {sentence}")

        return "\n".join(summary_parts)

    def _extract_json(self, response_text: str) -> dict[str, Any]:
        """
        Extract JSON from LLM response (handles markdown blocks).

        Args:
            response_text: Raw LLM response

        Returns:
            Parsed JSON dict

        Raises:
            json.JSONDecodeError: If no valid JSON found
        """
        text = response_text.strip()

        # Try direct parse
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        # Try markdown code block
        code_block_pattern = r"```(?:json)?\s*\n?([\s\S]*?)\n?```"
        matches = re.findall(code_block_pattern, text)
        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue

        # Try finding JSON anywhere
        json_pattern = r"\{[\s\S]*\}"
        json_matches = re.findall(json_pattern, text)
        for match in json_matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

        raise json.JSONDecodeError("No valid JSON found", text, 0)

    def _parse_output(self, raw: dict[str, Any]) -> ContentClassificationOutput:
        """
        Parse raw JSON into validated ContentClassificationOutput.

        Args:
            raw: Raw JSON dict from LLM

        Returns:
            Validated ContentClassificationOutput
        """
        # Parse signals
        signals = []
        for sig_data in raw.get("signals", []):
            try:
                sig = SignalClassification(
                    kind=sig_data.get("kind", "sentiment"),
                    state=sig_data.get("state", "warn"),
                    sentence=sig_data.get("sentence", "")[:200],
                    evidence_text=sig_data.get("evidence_text", "")[:500] if sig_data.get("evidence_text") else None,
                    confidence=float(sig_data.get("confidence", 0.5)),
                    reasoning=sig_data.get("reasoning"),
                )
                signals.append(sig)
            except (ValueError, KeyError) as e:
                logger.warning(
                    "signal_parse_error",
                    error=str(e),
                    signal_data=sig_data,
                )
                continue

        # Parse commitments
        commitments = []
        for commit_data in raw.get("commitments", []):
            try:
                # Normalize "who" field - handle cases where LLM returns names instead of "us"/"them"
                who_raw = commit_data.get("who", "them")
                if who_raw not in ("us", "them"):
                    # Try to infer from the content
                    who_lower = who_raw.lower()
                    # Common CSM/company names, team references
                    if any(keyword in who_lower for keyword in ["marcus", "northcrest", "we", "our", "team", "i'll", "csm"]):
                        who = "us"
                    else:
                        who = "them"
                    logger.debug(
                        "commitment_who_normalized",
                        original=who_raw,
                        normalized=who,
                    )
                else:
                    who = who_raw

                commit = CommitmentExtraction(
                    what=commit_data.get("what", "")[:500],
                    who=who,
                    due_date=commit_data.get("due_date"),
                    confidence=float(commit_data.get("confidence", 0.5)),
                )
                commitments.append(commit)
            except (ValueError, KeyError) as e:
                logger.warning(
                    "commitment_parse_error",
                    error=str(e),
                    commitment_data=commit_data,
                )
                continue

        return ContentClassificationOutput(
            signals=signals,
            commitments=commitments,
            suggested_need_type=raw.get("suggested_need_type"),
            overall_confidence=float(raw.get("overall_confidence", 0.0)),
            extraction_notes=raw.get("extraction_notes"),
        )

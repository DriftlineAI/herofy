"""
Signal to Need Mapper

Business rules for mapping detected signals to Need types.
Determines when signals should auto-create Needs in the Today Queue.
"""

from core.logging import get_logger
from .models import SignalClassification

logger = get_logger("SignalToNeedMapper")


class SignalToNeedMapper:
    """
    Business rules for mapping signals to need types.

    Confidence thresholds:
    - >= 0.7: Auto-create Need (appears in Today Queue)
    - 0.5-0.7: Create Signal only (tracking mode)
    - < 0.5: Skip (routine interaction, no action needed)
    """

    # Confidence thresholds
    CONFIDENCE_THRESHOLD_AUTO_NEED = 0.7
    CONFIDENCE_THRESHOLD_SIGNAL = 0.5

    # Signal (kind, state) → NeedType mapping rules
    SIGNAL_TO_NEED_RULES: dict[tuple[str, str], str] = {
        # Sentiment signals
        ("sentiment", "risk"): "frustrated_signal",
        ("sentiment", "warn"): "check_in_due",
        ("sentiment", "ok"): "positive_signal",  # Only for explicit positive feedback

        # Engagement signals
        ("engagement", "risk"): "going_dark",
        ("engagement", "warn"): "check_in_due",
        # engagement/ok typically doesn't need a Need

        # Commitment signals
        ("commitments", "risk"): "open_commitment_overdue",
        ("commitments", "warn"): "check_in_due",
        # commitments/ok typically doesn't need a Need
    }

    # Urgent need types that get high priority (low rank number)
    URGENT_NEED_TYPES = frozenset([
        "urgent_support",
        "frustrated_signal",
        "champion_departed",
        "open_commitment_overdue",
    ])

    def should_create_need(self, signal: SignalClassification) -> bool:
        """
        Check if signal confidence warrants auto-need creation.

        Args:
            signal: The classified signal

        Returns:
            True if Need should be auto-created
        """
        return signal.confidence >= self.CONFIDENCE_THRESHOLD_AUTO_NEED

    def should_create_signal(self, signal: SignalClassification) -> bool:
        """
        Check if signal should be recorded (even if no need).

        Args:
            signal: The classified signal

        Returns:
            True if Signal should be created
        """
        return signal.confidence >= self.CONFIDENCE_THRESHOLD_SIGNAL

    def map_signal_to_need_type(
        self,
        signal: SignalClassification,
        suggested_need_type: str | None = None,
    ) -> str:
        """
        Map signal to need type using business rules.

        Priority:
        1. Use LLM's suggested_need_type if confidence > 0.75
        2. Apply signal kind+state mapping rules
        3. Default to uncategorized

        Args:
            signal: The classified signal
            suggested_need_type: LLM's suggestion (if any)

        Returns:
            Need type string
        """
        # Priority 1: LLM suggestion (if high confidence)
        if suggested_need_type and signal.confidence >= 0.75:
            logger.debug(
                "using_llm_suggested_need",
                suggested_need=suggested_need_type,
                confidence=signal.confidence,
            )
            return suggested_need_type

        # Priority 2: Rule-based mapping
        rule_key = (signal.kind, signal.state)
        if rule_key in self.SIGNAL_TO_NEED_RULES:
            need_type = self.SIGNAL_TO_NEED_RULES[rule_key]
            logger.debug(
                "mapped_signal_to_need",
                kind=signal.kind,
                state=signal.state,
                need_type=need_type,
            )
            return need_type

        # Priority 3: Default
        logger.debug(
            "unmapped_signal_defaulting",
            kind=signal.kind,
            state=signal.state,
        )
        return "uncategorized"

    def determine_need_priority(self, signal: SignalClassification, need_type: str) -> int:
        """
        Calculate priority rank for need (lower = more urgent).

        Priority factors:
        - Urgent need types get rank 5-15
        - Normal need types get rank 50-100
        - Higher confidence gets lower (more urgent) rank

        Args:
            signal: The classified signal
            need_type: The mapped need type

        Returns:
            Priority rank (1-100, lower is more urgent)
        """
        # Base priority based on urgency
        if need_type in self.URGENT_NEED_TYPES:
            # Urgent: rank 5-15 based on confidence
            base_priority = 5
            confidence_adjustment = int((1 - signal.confidence) * 10)
        elif signal.state == "risk":
            # Risk state: rank 10-25
            base_priority = 10
            confidence_adjustment = int((1 - signal.confidence) * 15)
        elif signal.state == "warn":
            # Warn state: rank 40-60
            base_priority = 40
            confidence_adjustment = int((1 - signal.confidence) * 20)
        else:
            # Normal: rank 70-100
            base_priority = 70
            confidence_adjustment = int((1 - signal.confidence) * 30)

        priority = base_priority + confidence_adjustment

        logger.debug(
            "priority_calculated",
            need_type=need_type,
            signal_state=signal.state,
            confidence=signal.confidence,
            priority=priority,
        )

        return max(1, min(100, priority))  # Clamp to 1-100

    def should_skip_positive_signal(self, signal: SignalClassification) -> bool:
        """
        Check if a positive signal should skip Need creation.

        Positive signals (sentiment/ok) often don't need explicit action.
        Only create Need for positive signals if:
        - Very high confidence (>0.85)
        - Evidence of expansion interest

        Args:
            signal: The classified signal

        Returns:
            True if this positive signal should NOT create a Need
        """
        if signal.kind == "sentiment" and signal.state == "ok":
            # Skip unless very high confidence or expansion signal
            if signal.confidence < 0.85:
                logger.debug(
                    "skipping_low_confidence_positive",
                    confidence=signal.confidence,
                )
                return True

        return False

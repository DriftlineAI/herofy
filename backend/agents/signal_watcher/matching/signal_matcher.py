"""
Signal Matcher
Logic for matching signals to existing threads and needs
"""

from datetime import datetime, timedelta
from typing import Any

from db.dataconnect_client import get_dataconnect_client
from core.logging import get_logger
from ..models import (
    RawSignal,
    ClassifiedSignal,
    ThreadMatch,
    NeedMatch,
    MatchType,
)
from .similarity import calculate_subject_similarity, calculate_term_overlap

logger = get_logger("SignalMatcher")

# Match settings
INFERRED_MATCH_THRESHOLD = 0.6  # Minimum similarity for inferred match
INFERRED_MATCH_DAYS = 7  # Only look at threads from last N days
HIGH_CONFIDENCE_THRESHOLD = 0.8  # Above this = high confidence


class SignalMatcher:
    """
    Matches signals to existing threads and needs.

    Supports two matching modes:
    1. Explicit: Uses reply-to IDs, thread IDs
    2. Inferred: Uses subject similarity + timeframe

    For inferred matches, returns confidence score so UI can
    offer reassignment option.
    """

    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id
        self.dc = get_dataconnect_client()

    async def match_signal_to_thread(
        self,
        signal: RawSignal,
        customer_id: str,
    ) -> ThreadMatch | None:
        """
        Match a signal to an existing thread.

        First tries explicit matching (reply_to_id), then falls back
        to inferred matching (subject similarity).

        Args:
            signal: The signal to match
            customer_id: Customer UUID to scope search

        Returns:
            ThreadMatch if found, None otherwise
        """
        # Try explicit match first
        explicit_match = await self._match_explicit(signal, customer_id)
        if explicit_match:
            logger.info(
                "thread_match_explicit",
                signal_id=signal.id,
                thread_id=explicit_match.thread_id,
            )
            return explicit_match

        # Try inferred match
        inferred_match = await self._match_inferred(signal, customer_id)
        if inferred_match:
            logger.info(
                "thread_match_inferred",
                signal_id=signal.id,
                thread_id=inferred_match.thread_id,
                confidence=inferred_match.confidence,
            )
            return inferred_match

        logger.debug("no_thread_match", signal_id=signal.id)
        return None

    async def match_signal_to_need(
        self,
        signal: ClassifiedSignal,
        customer_id: str,
        thread_id: str | None = None,
    ) -> NeedMatch | None:
        """
        Match a signal to an existing need.

        If thread is provided, looks up need via thread.need_id.
        Otherwise, searches for open needs of same type for customer.

        Args:
            signal: Classified signal with need_type
            customer_id: Customer UUID
            thread_id: Optional thread UUID to get need from

        Returns:
            NeedMatch if found, None otherwise
        """
        # If we have a thread, get its need
        if thread_id:
            need = await self._get_need_by_thread(thread_id)
            if need:
                return NeedMatch(
                    need_id=str(need["id"]),
                    need_type=need["type"],
                    confidence=1.0,
                    reason="Thread is linked to this need",
                    need_headline=need.get("headline"),
                )

        # Search for matching open need by type
        if signal.classification:
            need_type = signal.classification.need_type
            need = await self._find_matching_need(customer_id, need_type)
            if need:
                return NeedMatch(
                    need_id=str(need["id"]),
                    need_type=need["type"],
                    confidence=0.7,
                    reason=f"Open {need_type} need exists for this customer",
                    need_headline=need.get("headline"),
                )

        return None

    async def find_customer_by_email(self, email: str) -> dict[str, Any] | None:
        """
        Find a customer by stakeholder email domain.

        Args:
            email: Sender email address

        Returns:
            Customer record if found
        """
        if not email or "@" not in email:
            return None

        domain = email.split("@")[1].lower()

        # Look up customer by email domain using DataConnect
        result = await self.dc.execute_query(
            "GetCustomerByDomain",
            {
                "workspaceId": self.workspace_id,
                "domain": domain,
            },
        )

        customer = result.get("customer")
        return customer

    async def _match_explicit(
        self,
        signal: RawSignal,
        customer_id: str,
    ) -> ThreadMatch | None:
        """
        Try to match signal using explicit references (reply-to, thread ID).
        """
        # Check reply-to ID against interactions
        if signal.reply_to_id:
            result = await self.dc.execute_query(
                "FindInteractionByExternalRef",
                {
                    "workspaceId": self.workspace_id,
                    "customerId": customer_id,
                    "messageId": signal.reply_to_id,
                },
            )

            interactions = result.get("interactions", [])
            if interactions:
                interaction = interactions[0]
                thread = interaction.get("thread")
                if thread:
                    return ThreadMatch(
                        thread_id=str(thread["id"]),
                        match_type=MatchType.EXPLICIT,
                        confidence=1.0,
                        reason="Matched via In-Reply-To header",
                        thread_subject=thread.get("subject"),
                    )

        # Check external thread ID (Slack thread_ts)
        if signal.thread_id:
            result = await self.dc.execute_query(
                "FindThreadByOriginDetail",
                {
                    "workspaceId": self.workspace_id,
                    "customerId": customer_id,
                    "originDetail": signal.thread_id,
                },
            )

            threads = result.get("threads", [])
            if threads:
                thread = threads[0]
                return ThreadMatch(
                    thread_id=str(thread["id"]),
                    match_type=MatchType.EXPLICIT,
                    confidence=1.0,
                    reason="Matched via external thread reference",
                    thread_subject=thread.get("subject"),
                )

        return None

    async def _match_inferred(
        self,
        signal: RawSignal,
        customer_id: str,
    ) -> ThreadMatch | None:
        """
        Try to match signal using subject similarity and timeframe.
        """
        if not signal.subject:
            return None

        # Get recent threads for this customer
        cutoff = datetime.utcnow() - timedelta(days=INFERRED_MATCH_DAYS)

        result = await self.dc.execute_query(
            "FindRecentOpenThreads",
            {
                "workspaceId": self.workspace_id,
                "customerId": customer_id,
                "afterDate": cutoff.isoformat(),
                "limit": 20,
            },
        )

        recent_threads = result.get("threads", [])
        if not recent_threads:
            return None

        # Score each thread
        best_match = None
        best_score = 0.0

        for thread in recent_threads:
            thread_subject = thread.get("subject")
            if not thread_subject:
                continue

            # Calculate subject similarity
            similarity = calculate_subject_similarity(signal.subject, thread_subject)

            # Boost score if body has term overlap with subject
            if signal.body and thread_subject:
                term_overlap = calculate_term_overlap(signal.body, thread_subject)
                similarity = (similarity * 0.7) + (term_overlap * 0.3)

            if similarity > best_score and similarity >= INFERRED_MATCH_THRESHOLD:
                best_score = similarity
                best_match = thread

        if best_match:
            return ThreadMatch(
                thread_id=str(best_match["id"]),
                match_type=MatchType.INFERRED,
                confidence=best_score,
                reason=f"Subject similarity: {best_score:.0%}",
                thread_subject=best_match.get("subject"),
            )

        return None

    async def _get_need_by_thread(self, thread_id: str) -> dict[str, Any] | None:
        """Get the need linked to a thread."""
        result = await self.dc.execute_query(
            "GetNeedByThread",
            {
                "threadId": thread_id,
                "workspaceId": self.workspace_id,
            },
        )

        threads = result.get("threads", [])
        if threads and threads[0].get("need"):
            need = threads[0]["need"]
            # Only return if not resolved
            if not need.get("resolvedAt"):
                return need

        return None

    async def _find_matching_need(
        self,
        customer_id: str,
        need_type: str,
    ) -> dict[str, Any] | None:
        """Find an open need of the same type for a customer."""
        result = await self.dc.execute_query(
            "FindOpenNeedByType",
            {
                "workspaceId": self.workspace_id,
                "customerId": customer_id,
                "needType": need_type,
            },
        )

        needs = result.get("needs", [])
        return needs[0] if needs else None

    async def get_recent_threads_for_customer(
        self,
        customer_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Get recent threads for a customer (for UI display).

        Args:
            customer_id: Customer UUID
            limit: Max threads to return

        Returns:
            List of thread records
        """
        result = await self.dc.execute_query(
            "GetRecentThreadsForCustomer",
            {
                "workspaceId": self.workspace_id,
                "customerId": customer_id,
                "limit": limit,
            },
        )

        return result.get("threads", [])

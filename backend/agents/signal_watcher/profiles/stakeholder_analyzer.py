"""
Stakeholder Analyzer
Extracts full stakeholder profiles from signals and interaction history
"""

import re
from datetime import datetime, timedelta
from typing import Any

from db.dataconnect_client import get_dataconnect_client
from core.logging import get_logger
from ..models import (
    RawSignal,
    StakeholderProfile,
    Sentiment,
    CommunicationStyle,
    EngagementLevel,
    ResponsePattern,
    Classification,
)

logger = get_logger("StakeholderAnalyzer")


class StakeholderAnalyzer:
    """
    Analyzes signals to extract comprehensive stakeholder profiles.

    Extracts:
    - Sentiment from message content
    - Communication style (formal/casual/technical)
    - Response patterns from interaction history
    - Engagement level from activity frequency
    - Role inference from signature/content

    Note: Interaction analytics queries remain as SQL for performance.
    Only stakeholder CRUD operations use DataConnect.
    """

    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id
        self.dc = get_dataconnect_client()

        # Keep db for complex analytics queries (interaction history, response times)
        # These are read-only analytical queries that are performant in SQL
        from db.client import get_db_client
        self._db_analytics = get_db_client()

    async def analyze_stakeholder(
        self,
        signal: RawSignal,
        classification: Classification | None,
        customer_id: str,
    ) -> StakeholderProfile:
        """
        Analyze a signal to extract/update stakeholder profile.

        Args:
            signal: The raw signal to analyze
            classification: Optional classification for sentiment
            customer_id: Customer UUID

        Returns:
            StakeholderProfile with extracted attributes
        """
        # Start with basic info
        profile = StakeholderProfile(
            name=signal.sender_name,
            email=signal.sender_email,
        )

        # Extract role from signature
        profile.role = self._extract_role(signal.body)

        # Determine sentiment
        if classification:
            profile.sentiment = classification.sentiment
            profile.sentiment_note = self._build_sentiment_note(
                classification.sentiment,
                classification.keywords,
            )
        else:
            profile.sentiment = self._detect_sentiment(signal.body)

        # Analyze communication style
        profile.communication_style = self._analyze_style(signal.body)

        # Check if technical
        profile.is_technical = self._detect_technical(signal.body)

        # Check if decision maker
        profile.is_decision_maker = self._detect_decision_maker(
            signal.body,
            profile.role,
        )

        # Get historical metrics
        if signal.sender_email:
            history = await self._get_interaction_history(
                signal.sender_email,
                customer_id,
            )
            if history:
                profile.response_pattern = self._calculate_response_pattern(history)
                profile.engagement_level = self._calculate_engagement(history)
                profile.avg_response_hours = history.get("avg_response_hours")
                profile.interaction_count = history.get("count", 0)
                profile.last_interaction_at = history.get("last_interaction_at")
                profile.timezone_inference = self._infer_timezone(history)

        logger.debug(
            "stakeholder_analyzed",
            name=profile.name,
            sentiment=profile.sentiment.value,
            style=profile.communication_style.value,
        )

        return profile

    def _extract_role(self, body: str) -> str | None:
        """
        Extract role/title from email signature.

        Looks for common patterns:
        - Name<newline>Title
        - Title | Company
        - Sent from my iPhone (filters)
        """
        if not body:
            return None

        # Common title patterns
        title_patterns = [
            # Common C-suite/VP titles
            r"\b(CEO|CTO|CFO|COO|CMO|CIO|CPO)\b",
            r"\b(Chief\s+\w+\s+Officer)\b",
            r"\b(Vice\s+President|VP)\s+(of\s+)?\w+\b",
            r"\b(Director)\s+(of\s+)?\w+\b",
            r"\b(Head\s+of)\s+\w+\b",
            r"\b(Manager|Lead|Engineer|Developer|Analyst|Consultant)\b",
            # Signature line patterns
            r"\n([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*[,|\n]\s*([\w\s]+(?:Engineer|Manager|Director|VP|Lead|Head|Analyst|Developer|Designer))",
        ]

        for pattern in title_patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                return match.group(0).strip()

        return None

    def _detect_sentiment(self, body: str) -> Sentiment:
        """
        Detect sentiment from message body (fallback when no classification).
        """
        if not body:
            return Sentiment.NEUTRAL

        body_lower = body.lower()

        # Frustrated indicators
        frustrated_indicators = [
            "frustrated", "disappointed", "unacceptable", "ridiculous",
            "still waiting", "no response", "escalate", "!!",
        ]
        if any(ind in body_lower for ind in frustrated_indicators):
            return Sentiment.FRUSTRATED

        # Negative indicators
        negative_indicators = [
            "issue", "problem", "error", "not working", "broken",
            "concerned", "worried", "upset",
        ]
        if any(ind in body_lower for ind in negative_indicators):
            return Sentiment.NEGATIVE

        # Positive indicators
        positive_indicators = [
            "thank you", "thanks", "great", "love it", "amazing",
            "happy", "pleased", "impressed", "smooth",
        ]
        if any(ind in body_lower for ind in positive_indicators):
            return Sentiment.POSITIVE

        return Sentiment.NEUTRAL

    def _build_sentiment_note(
        self,
        sentiment: Sentiment,
        keywords: list[str],
    ) -> str:
        """Build human-readable sentiment note."""
        if sentiment == Sentiment.FRUSTRATED:
            if keywords:
                return f"Frustrated about: {', '.join(keywords[:3])}"
            return "Showing signs of frustration"
        elif sentiment == Sentiment.NEGATIVE:
            return "Expressing concerns"
        elif sentiment == Sentiment.POSITIVE:
            if keywords:
                return f"Positive about: {', '.join(keywords[:3])}"
            return "Generally positive sentiment"
        return ""

    def _analyze_style(self, body: str) -> CommunicationStyle:
        """
        Analyze communication style from message content.
        """
        if not body:
            return CommunicationStyle.FORMAL

        body_lower = body.lower()

        # Technical indicators
        technical_indicators = [
            "api", "endpoint", "database", "server", "deploy",
            "integration", "webhook", "json", "error code",
            "stack trace", "debug", "log", "config",
        ]
        technical_count = sum(1 for ind in technical_indicators if ind in body_lower)
        if technical_count >= 2:
            return CommunicationStyle.TECHNICAL

        # Casual indicators
        casual_indicators = [
            "hey", "hi!", "gonna", "wanna", "kinda", "btw",
            "lol", "haha", "yep", "nope", ":)", ":-)",
        ]
        casual_count = sum(1 for ind in casual_indicators if ind in body_lower)

        # Formal indicators
        formal_indicators = [
            "dear", "sincerely", "regards", "respectfully",
            "i would like to", "please find attached",
            "pursuant to", "as per our discussion",
        ]
        formal_count = sum(1 for ind in formal_indicators if ind in body_lower)

        # Check message length (brief = short messages)
        word_count = len(body.split())
        if word_count < 50 and casual_count > 0:
            return CommunicationStyle.BRIEF

        if casual_count > formal_count:
            return CommunicationStyle.CASUAL

        return CommunicationStyle.FORMAL

    def _detect_technical(self, body: str) -> bool:
        """Detect if the stakeholder appears to be technical."""
        if not body:
            return False

        technical_terms = [
            "api", "endpoint", "database", "server", "deploy",
            "integration", "webhook", "json", "xml", "sdk",
            "authentication", "oauth", "jwt", "token",
            "debug", "stack trace", "error log", "config",
        ]

        body_lower = body.lower()
        count = sum(1 for term in technical_terms if term in body_lower)
        return count >= 2

    def _detect_decision_maker(self, body: str, role: str | None) -> bool:
        """Detect if the stakeholder is likely a decision maker."""
        decision_maker_roles = [
            "ceo", "cto", "cfo", "coo", "cmo", "cpo",
            "chief", "president", "vp", "vice president",
            "director", "head of", "owner", "founder",
        ]

        if role:
            role_lower = role.lower()
            if any(dm in role_lower for dm in decision_maker_roles):
                return True

        # Check body for decision-making language
        decision_indicators = [
            "i've decided", "we're going to", "approved",
            "let's move forward", "final decision",
            "budget for", "sign off", "executive team",
        ]

        if body:
            body_lower = body.lower()
            if any(ind in body_lower for ind in decision_indicators):
                return True

        return False

    async def _get_interaction_history(
        self,
        email: str,
        customer_id: str,
    ) -> dict[str, Any] | None:
        """
        Get interaction history stats for a stakeholder.
        """
        # Get interaction stats - match by email or sender name with email prefix
        # Use case-insensitive email match for accuracy
        stats = await self._db_analytics.query_one(
            """
            SELECT
                COUNT(*) as count,
                MAX(occurred_at) as last_interaction_at,
                array_agg(DISTINCT EXTRACT(HOUR FROM occurred_at)) as hours
            FROM interactions
            WHERE workspace_id = $1
              AND customer_id = $2
              AND (
                -- Exact email match (case-insensitive)
                LOWER(
                    COALESCE(
                        external_ref->>'sender_email',
                        external_ref->>'email'
                    )
                ) = LOWER($3)
                -- Fallback: sender name contains email username
                OR sender_name ILIKE '%' || split_part($3, '@', 1) || '%'
              )
              AND occurred_at > NOW() - INTERVAL '90 days'
            """,
            [self.workspace_id, customer_id, email],
        )

        if not stats or stats.get("count", 0) == 0:
            return None

        # Calculate average response time (simplified)
        # In production, would compare to outgoing messages
        avg_response_hours = await self._calculate_avg_response_time(
            email,
            customer_id,
        )

        return {
            "count": stats.get("count", 0),
            "last_interaction_at": stats.get("last_interaction_at"),
            "hours": stats.get("hours", []),
            "avg_response_hours": avg_response_hours,
        }

    async def _calculate_avg_response_time(
        self,
        email: str,
        customer_id: str,
    ) -> float | None:
        """
        Calculate average response time in hours.

        Simplified: looks at time between our messages and their replies.
        """
        # Get pairs of (our message, their reply) to calculate response time
        result = await self._db_analytics.query_one(
            """
            WITH our_messages AS (
                SELECT occurred_at, id FROM interactions
                WHERE workspace_id = $1 AND customer_id = $2
                  AND direction = 'us'
                ORDER BY occurred_at DESC
                LIMIT 20
            ),
            their_replies AS (
                SELECT occurred_at FROM interactions
                WHERE workspace_id = $1 AND customer_id = $2
                  AND direction = 'customer'
                  AND (
                    -- Exact email match (case-insensitive)
                    LOWER(
                        COALESCE(
                            external_ref->>'sender_email',
                            external_ref->>'email'
                        )
                    ) = LOWER($3)
                    -- Fallback: sender name contains email username
                    OR sender_name ILIKE '%' || split_part($3, '@', 1) || '%'
                  )
            )
            SELECT AVG(
                EXTRACT(EPOCH FROM (tr.occurred_at - om.occurred_at)) / 3600
            ) as avg_hours
            FROM our_messages om
            JOIN LATERAL (
                SELECT occurred_at FROM their_replies
                WHERE occurred_at > om.occurred_at
                ORDER BY occurred_at
                LIMIT 1
            ) tr ON true
            WHERE EXTRACT(EPOCH FROM (tr.occurred_at - om.occurred_at)) / 3600 < 168
            """,
            [self.workspace_id, customer_id, email],
        )

        return result.get("avg_hours") if result else None

    def _calculate_response_pattern(
        self,
        history: dict[str, Any],
    ) -> ResponsePattern:
        """Determine response pattern from history."""
        avg_hours = history.get("avg_response_hours")

        if avg_hours is None:
            return ResponsePattern.VARIABLE

        if avg_hours < 1:
            return ResponsePattern.FAST
        elif avg_hours < 4:
            return ResponsePattern.NORMAL
        else:
            return ResponsePattern.SLOW

    def _calculate_engagement(
        self,
        history: dict[str, Any],
    ) -> EngagementLevel:
        """Calculate engagement level from interaction frequency."""
        count = history.get("count", 0)
        last_interaction = history.get("last_interaction_at")

        if not last_interaction:
            return EngagementLevel.LOW

        # Check recency
        days_since = (datetime.utcnow() - last_interaction).days

        if days_since > 30 or count < 2:
            return EngagementLevel.DISENGAGED
        elif days_since > 14 and count < 5:
            return EngagementLevel.LOW
        elif count >= 10 and days_since < 7:
            return EngagementLevel.HIGH
        else:
            return EngagementLevel.MEDIUM

    def _infer_timezone(self, history: dict[str, Any]) -> str | None:
        """
        Infer timezone from message send times.

        Assumes most people send messages during business hours (9-18).
        """
        hours = history.get("hours", [])
        if not hours or len(hours) < 3:
            return None

        # Filter to valid hours
        valid_hours = [h for h in hours if h is not None]
        if not valid_hours:
            return None

        avg_hour = sum(valid_hours) / len(valid_hours)

        # Map average hour to likely timezone
        # Assumes sender is in US timezones
        if 9 <= avg_hour <= 12:
            return "PST/PDT"
        elif 12 <= avg_hour <= 15:
            return "MST/MDT or PST/PDT"
        elif 15 <= avg_hour <= 18:
            return "CST/CDT or EST/EDT"
        elif 18 <= avg_hour <= 21:
            return "EST/EDT"

        return None

    async def update_stakeholder_record(
        self,
        customer_id: str,
        profile: StakeholderProfile,
    ) -> dict[str, Any] | None:
        """
        Update or create stakeholder record in database.

        Args:
            customer_id: Customer UUID
            profile: Extracted profile

        Returns:
            Updated stakeholder record
        """
        if not profile.email:
            return None

        # Check if stakeholder exists using DataConnect
        result = await self.dc.execute_query(
            "GetStakeholderByEmail",
            {
                "workspaceId": self.workspace_id,
                "email": profile.email,
            },
        )

        existing = result.get("stakeholder")

        sentiment_note = profile.sentiment_note or ""
        if profile.communication_style != CommunicationStyle.FORMAL:
            sentiment_note += f" Style: {profile.communication_style.value}"

        if existing and existing.get("customer", {}).get("id") == customer_id:
            # Update existing using DataConnect
            update_result = await self.dc.execute_mutation(
                "UpdateStakeholder",
                {
                    "id": existing["id"],
                    "sentimentNote": sentiment_note,
                    "role": profile.role or existing.get("role"),
                },
            )
            # lastInteractionAt is a single-field touch (UpdateStakeholder doesn't
            # carry it; bundling it there would also risk nulling other columns).
            await self.dc.execute_mutation(
                "TouchStakeholderLastInteraction",
                {
                    "id": existing["id"],
                    "lastInteractionAt": (profile.last_interaction_at or datetime.utcnow()).isoformat(),
                },
            )
            return update_result.get("stakeholder_update")
        else:
            # Create new using DataConnect
            import uuid
            create_result = await self.dc.execute_mutation(
                "CreateStakeholderIfNotExists",
                {
                    "id": str(uuid.uuid4()),
                    "workspaceId": self.workspace_id,
                    "customerId": customer_id,
                    "name": profile.name,
                    "email": profile.email,
                    "role": profile.role,
                    "sentimentNote": sentiment_note,
                    "status": "active",
                },
            )
            return create_result.get("stakeholder_insert")

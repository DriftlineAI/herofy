"""
Mock Signal Sources
Deterministic mock data for development and testing
"""

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from ..models import RawSignal, SignalSource
from .base import SignalSourceBase


class MockGmailSource(SignalSourceBase):
    """
    Mock Gmail source with deterministic test data.

    Provides realistic email signals for testing the signal watcher pipeline.
    """

    def _get_source_type(self) -> SignalSource:
        return SignalSource.GMAIL

    async def fetch_signals(self, since: datetime | None = None) -> list[RawSignal]:
        """Return mock Gmail signals."""
        now = datetime.utcnow()

        # Mock signals with various scenarios
        signals = [
            # Urgent support request
            RawSignal(
                id=str(uuid4()),
                source=SignalSource.GMAIL,
                external_id=f"gmail-msg-{uuid4().hex[:8]}",
                sender_email="john.smith@techcorp.com",
                sender_name="John Smith",
                sender_domain="techcorp.com",
                subject="URGENT: Integration broken in production",
                body="""Hi team,

Our production integration has been down since this morning. Users are unable to sync data and our executives are asking questions.

We need immediate assistance. This is blocking our Q1 launch.

Can someone look into this ASAP?

Thanks,
John Smith
VP of Engineering
TechCorp Solutions""",
                channel="email",
                occurred_at=now - timedelta(hours=2),
                raw_metadata={"labels": ["INBOX", "IMPORTANT"]},
            ),
            # Positive signal - expansion interest
            RawSignal(
                id=str(uuid4()),
                source=SignalSource.GMAIL,
                external_id=f"gmail-msg-{uuid4().hex[:8]}",
                sender_email="sarah.chen@globex.com",
                sender_name="Sarah Chen",
                sender_domain="globex.com",
                subject="Re: Adding more seats to our account",
                body="""Hi there,

Great news! Our team loved the demo last week. We'd like to expand from 10 to 50 seats.

Can you send over updated pricing? We're looking to finalize this before end of month.

Best,
Sarah""",
                channel="email",
                reply_to_id="gmail-thread-expansion-001",
                occurred_at=now - timedelta(hours=5),
                raw_metadata={"labels": ["INBOX"]},
            ),
            # Going dark signal - follow-up needed
            RawSignal(
                id=str(uuid4()),
                source=SignalSource.GMAIL,
                external_id=f"gmail-msg-{uuid4().hex[:8]}",
                sender_email="alerts@herofy.io",
                sender_name="Herofy System",
                sender_domain="herofy.io",
                subject="No response from Acme Corp in 14 days",
                body="""Customer Alert:

Acme Corp has not responded to the last 3 emails:
- Onboarding check-in (sent 14 days ago)
- Feature demo follow-up (sent 10 days ago)
- Monthly review scheduling (sent 7 days ago)

Last activity: Mike Johnson opened the onboarding email 12 days ago.

Recommend: Direct outreach or phone call.""",
                channel="email",
                occurred_at=now - timedelta(hours=1),
                raw_metadata={"labels": ["INTERNAL", "ALERT"]},
            ),
            # Frustrated customer
            RawSignal(
                id=str(uuid4()),
                source=SignalSource.GMAIL,
                external_id=f"gmail-msg-{uuid4().hex[:8]}",
                sender_email="david.miller@acme.com",
                sender_name="David Miller",
                sender_domain="acme.com",
                subject="Re: Still waiting on the fix",
                body="""This is getting ridiculous.

I've been waiting THREE WEEKS for this bug fix. Every time I ask, I get the same "it's on the roadmap" response.

We're paying $50k/year for this and can't even get basic issues resolved. I'm going to have to escalate this to our CTO if we don't see progress this week.

Very disappointed.

David""",
                channel="email",
                reply_to_id="gmail-thread-bug-fix-001",
                occurred_at=now - timedelta(minutes=30),
                raw_metadata={"labels": ["INBOX", "STARRED"]},
            ),
            # Routine check-in reply
            RawSignal(
                id=str(uuid4()),
                source=SignalSource.GMAIL,
                external_id=f"gmail-msg-{uuid4().hex[:8]}",
                sender_email="lisa.wong@newcustomer.io",
                sender_name="Lisa Wong",
                sender_domain="newcustomer.io",
                subject="Re: Week 2 check-in",
                body="""Hi!

Thanks for checking in. Everything is going great so far! The team has completed the first two training modules and we're ahead of schedule.

Quick question: When do we get access to the advanced analytics dashboard?

Cheers,
Lisa""",
                channel="email",
                reply_to_id="gmail-thread-onboarding-001",
                occurred_at=now - timedelta(hours=3),
                raw_metadata={"labels": ["INBOX"]},
            ),
        ]

        # Filter by watermark if provided
        if since:
            signals = [s for s in signals if s.occurred_at > since]

        return signals


class MockSlackSource(SignalSourceBase):
    """
    Mock Slack source with deterministic test data.

    Provides realistic Slack message signals.
    """

    def _get_source_type(self) -> SignalSource:
        return SignalSource.SLACK

    async def fetch_signals(self, since: datetime | None = None) -> list[RawSignal]:
        """Return mock Slack signals."""
        now = datetime.utcnow()

        signals = [
            # Escalation in shared channel
            RawSignal(
                id=str(uuid4()),
                source=SignalSource.SLACK,
                external_id=f"slack-{uuid4().hex[:8]}",
                sender_email="ops@techcorp.com",
                sender_name="TechCorp Ops Team",
                sender_domain="techcorp.com",
                subject="Question in #techcorp-support",
                body="""@hero-support Our CEO is asking about the outage this morning. Can we get on a call in the next hour? This needs executive attention.""",
                channel="slack",
                thread_id="thread-escalation-001",
                occurred_at=now - timedelta(hours=1),
                raw_metadata={
                    "channel_name": "techcorp-support",
                    "mentions": ["hero-support"],
                },
            ),
            # Quick question
            RawSignal(
                id=str(uuid4()),
                source=SignalSource.SLACK,
                external_id=f"slack-{uuid4().hex[:8]}",
                sender_email="engineer@globex.com",
                sender_name="Alex Developer",
                sender_domain="globex.com",
                subject="Question in #globex-onboarding",
                body="Hey! Quick question - where do I find the API docs for the new endpoint? Can't seem to locate them in the knowledge base.",
                channel="slack",
                occurred_at=now - timedelta(hours=4),
                raw_metadata={"channel_name": "globex-onboarding"},
            ),
            # Praise message
            RawSignal(
                id=str(uuid4()),
                source=SignalSource.SLACK,
                external_id=f"slack-{uuid4().hex[:8]}",
                sender_email="pm@newcustomer.io",
                sender_name="Product Manager",
                sender_domain="newcustomer.io",
                subject="Message in #newcustomer-general",
                body="Just wanted to say the new feature release is amazing! Our team is loving the improvements. Great work! :tada: :heart:",
                channel="slack",
                occurred_at=now - timedelta(hours=6),
                raw_metadata={"channel_name": "newcustomer-general"},
            ),
        ]

        if since:
            signals = [s for s in signals if s.occurred_at > since]

        return signals


class MockNotionSource(SignalSourceBase):
    """
    Mock Notion source for comments and updates.
    """

    def _get_source_type(self) -> SignalSource:
        return SignalSource.NOTION

    async def fetch_signals(self, since: datetime | None = None) -> list[RawSignal]:
        """Return mock Notion signals."""
        now = datetime.utcnow()

        signals = [
            # Comment on project page
            RawSignal(
                id=str(uuid4()),
                source=SignalSource.NOTION,
                external_id=f"notion-comment-{uuid4().hex[:8]}",
                sender_email="pm@techcorp.com",
                sender_name="TechCorp PM",
                sender_domain="techcorp.com",
                subject="Comment on: TechCorp Implementation Plan",
                body="We need to revisit the timeline for Phase 2. Our engineering team is tied up with another project until March. Can we push milestone 4 by 2 weeks?",
                channel="note",
                occurred_at=now - timedelta(hours=8),
                raw_metadata={
                    "page_id": "notion-page-001",
                    "page_title": "TechCorp Implementation Plan",
                },
            ),
        ]

        if since:
            signals = [s for s in signals if s.occurred_at > since]

        return signals


def get_all_mock_sources(workspace_id: str) -> list[SignalSourceBase]:
    """
    Get instances of all mock signal sources.

    Args:
        workspace_id: The workspace UUID

    Returns:
        List of mock source instances
    """
    return [
        MockGmailSource(workspace_id),
        MockSlackSource(workspace_id),
        MockNotionSource(workspace_id),
    ]

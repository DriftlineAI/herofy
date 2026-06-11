"""
SignalWatcher Chain Agent Tests
Test that incoming signals flow through the processing pipeline correctly
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from agents.signal_watcher.models import (
    SignalSource,
    RawSignal,
    Classification,
    ClassifiedSignal,
    ThreadMatch,
    NeedMatch,
    MatchType,
    Sentiment,
    Urgency,
    StakeholderProfile,
    ProcessedSignal,
    SignalBatch,
    CommunicationStyle,
    EngagementLevel,
    ResponsePattern,
)
from agents.signal_watcher_legacy.context import SignalWatcherContext
from agents.signal_watcher_legacy.steps import (
    fetch_signals_step,
    classify_signals_step,
    match_threads_step,
    match_needs_step,
    extract_profiles_step,
    create_interactions_step,
    update_watermarks_step,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def workspace_id() -> str:
    """Test workspace ID."""
    return "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def mock_raw_signals() -> list[RawSignal]:
    """Sample raw signals for testing."""
    return [
        RawSignal(
            id="sig-001",
            source=SignalSource.GMAIL,
            external_id="gmail-123",
            occurred_at=datetime.utcnow(),
            sender_name="John Doe",
            sender_email="john@techcorp.com",
            subject="Urgent: Integration not working",
            body="Hi, our API integration has been failing since yesterday. "
                 "We're getting 500 errors. This is blocking our launch!",
            thread_id="thread-abc",
            reply_to_id=None,
        ),
        RawSignal(
            id="sig-002",
            source=SignalSource.SLACK,
            external_id="slack-456",
            occurred_at=datetime.utcnow(),
            sender_name="Jane Smith",
            sender_email="jane@acme.com",
            subject=None,
            body="Hey team, just wanted to say the new dashboard looks amazing! "
                 "Our executives are really impressed.",
            channel="support-acme",
            raw_metadata={"thread_ts": "1234567890.123456"},
        ),
        RawSignal(
            id="sig-003",
            source=SignalSource.NOTION,
            external_id="notion-789",
            occurred_at=datetime.utcnow(),
            sender_name="System",
            sender_email=None,
            subject="Customer Note Updated",
            body="TechCorp renewed for 3 years. Expansion opportunity discussed.",
            raw_metadata={"page_id": "notion-page-xyz"},
        ),
    ]


@pytest.fixture
def mock_classified_signals(mock_raw_signals) -> list[ClassifiedSignal]:
    """Sample classified signals for testing."""
    return [
        ClassifiedSignal(
            id=mock_raw_signals[0].id,
            source=mock_raw_signals[0].source,
            external_id=mock_raw_signals[0].external_id,
            occurred_at=mock_raw_signals[0].occurred_at,
            sender_name=mock_raw_signals[0].sender_name,
            sender_email=mock_raw_signals[0].sender_email,
            subject=mock_raw_signals[0].subject,
            body=mock_raw_signals[0].body,
            thread_id=mock_raw_signals[0].thread_id,
            customer_id="cust-techcorp",
            classification=Classification(
                need_type="urgent_support",
                sentiment=Sentiment.FRUSTRATED,
                urgency=Urgency.HIGH,
                confidence=0.92,
                keywords=["API", "integration", "failing", "500 errors", "blocking"],
            ),
        ),
        ClassifiedSignal(
            id=mock_raw_signals[1].id,
            source=mock_raw_signals[1].source,
            external_id=mock_raw_signals[1].external_id,
            occurred_at=mock_raw_signals[1].occurred_at,
            sender_name=mock_raw_signals[1].sender_name,
            sender_email=mock_raw_signals[1].sender_email,
            subject=mock_raw_signals[1].subject,
            body=mock_raw_signals[1].body,
            channel=mock_raw_signals[1].channel,
            raw_metadata=mock_raw_signals[1].raw_metadata,
            customer_id="cust-acme",
            classification=Classification(
                need_type="positive_signal",
                sentiment=Sentiment.POSITIVE,
                urgency=Urgency.LOW,
                confidence=0.88,
                keywords=["amazing", "impressed", "dashboard"],
            ),
        ),
        ClassifiedSignal(
            id=mock_raw_signals[2].id,
            source=mock_raw_signals[2].source,
            external_id=mock_raw_signals[2].external_id,
            occurred_at=mock_raw_signals[2].occurred_at,
            sender_name=mock_raw_signals[2].sender_name,
            sender_email=mock_raw_signals[2].sender_email,
            subject=mock_raw_signals[2].subject,
            body=mock_raw_signals[2].body,
            raw_metadata=mock_raw_signals[2].raw_metadata,
            customer_id="cust-techcorp",
            classification=Classification(
                need_type="expansion_signal",
                sentiment=Sentiment.POSITIVE,
                urgency=Urgency.MEDIUM,
                confidence=0.75,
                keywords=["renewed", "expansion"],
            ),
        ),
    ]


# =============================================================================
# Context Tests
# =============================================================================


@pytest.mark.asyncio
async def test_signal_watcher_context_initialization(workspace_id):
    """Test SignalWatcherContext creates with correct initial state."""
    ctx = SignalWatcherContext(workspace_id=workspace_id)

    assert ctx.workspace_id == workspace_id
    assert ctx.run_id is not None
    assert ctx.signal_count == 0
    assert len(ctx.raw_signals) == 0
    assert len(ctx.classified_signals) == 0
    assert len(ctx.thread_matches) == 0
    assert len(ctx.need_matches) == 0
    assert len(ctx.errors) == 0
    assert not ctx.is_failed


@pytest.mark.asyncio
async def test_signal_watcher_context_with_raw_signals(workspace_id, mock_raw_signals):
    """Test SignalWatcherContext.with_raw_signals returns new context."""
    ctx = SignalWatcherContext(workspace_id=workspace_id)

    batches = [
        SignalBatch(
            source=SignalSource.GMAIL,
            signals=[mock_raw_signals[0]],
            watermark_after=datetime.utcnow(),
        )
    ]

    new_ctx = ctx.with_raw_signals(batches, mock_raw_signals)

    assert new_ctx.signal_count == 3
    assert len(new_ctx.raw_signals) == 3
    assert new_ctx.run_id == ctx.run_id  # Same run


@pytest.mark.asyncio
async def test_signal_watcher_context_with_classified_signals(
    workspace_id, mock_classified_signals
):
    """Test SignalWatcherContext.with_classified_signals returns new context."""
    ctx = SignalWatcherContext(workspace_id=workspace_id)

    new_ctx = ctx.with_classified_signals(mock_classified_signals)

    assert len(new_ctx.classified_signals) == 3
    assert new_ctx.classified_signals[0].customer_id == "cust-techcorp"


@pytest.mark.asyncio
async def test_signal_watcher_context_error_tracking(workspace_id):
    """Test SignalWatcherContext tracks errors correctly."""
    ctx = SignalWatcherContext(workspace_id=workspace_id)

    error_ctx = ctx.with_error("FetchSignalsStep", "Connection timeout")

    assert error_ctx.is_failed
    assert error_ctx.failed_step == "FetchSignalsStep"
    assert "FetchSignalsStep: Connection timeout" in error_ctx.errors


@pytest.mark.asyncio
async def test_signal_watcher_context_serialization(workspace_id, mock_classified_signals):
    """Test context can be serialized and deserialized."""
    ctx = SignalWatcherContext(workspace_id=workspace_id)
    ctx = ctx.with_classified_signals(mock_classified_signals)

    # Serialize
    data = ctx.to_dict()
    assert data["workspace_id"] == workspace_id
    assert data["signal_count"] == 0  # Raw signals not added
    assert data["classified_count"] == 3

    # Deserialize
    restored = SignalWatcherContext.from_dict(data)
    assert restored.workspace_id == workspace_id
    assert restored.run_id == ctx.run_id


# =============================================================================
# Classification Tests
# =============================================================================


@pytest.mark.asyncio
async def test_classify_signals_step(workspace_id, mock_raw_signals):
    """Test ClassifySignalsStep classifies signals correctly."""
    ctx = SignalWatcherContext(workspace_id=workspace_id)
    ctx = ctx.with_raw_signals([], mock_raw_signals)

    # Mock the classifier and customer resolution
    with patch("agents.signal_watcher_chain.steps.RegexClassifier") as MockClassifier:
        with patch("agents.signal_watcher_chain.steps.SignalMatcher") as MockMatcher:
            # Setup classifier mock
            classifier_instance = MagicMock()
            classifier_instance.classify = MagicMock(
                return_value=Classification(
                    need_type="urgent_support",
                    sentiment=Sentiment.FRUSTRATED,
                    urgency=Urgency.HIGH,
                    confidence=0.9,
                    keywords=["urgent"],
                )
            )
            MockClassifier.return_value = classifier_instance

            # Setup matcher mock for customer resolution
            matcher_instance = MagicMock()
            matcher_instance.find_customer_by_email = AsyncMock(
                return_value="cust-123"
            )
            MockMatcher.return_value = matcher_instance

            result = await classify_signals_step(ctx)

            assert len(result.classified_signals) == 3
            # All signals should have classification
            for signal in result.classified_signals:
                assert signal.classification is not None
                assert signal.classification.need_type == "urgent_support"


# =============================================================================
# Thread Matching Tests
# =============================================================================


@pytest.mark.asyncio
async def test_match_threads_step_explicit_match(workspace_id, mock_classified_signals):
    """Test MatchThreadsStep finds explicit thread matches."""
    ctx = SignalWatcherContext(workspace_id=workspace_id)
    ctx = ctx.with_classified_signals(mock_classified_signals)

    with patch("agents.signal_watcher_chain.steps.get_db_client") as mock_db:
        mock_db.return_value = MagicMock()

        with patch("agents.signal_watcher_chain.steps.SignalMatcher") as MockMatcher:
            matcher_instance = MagicMock()
            # First signal has explicit match via thread_id
            matcher_instance.match_signal_to_thread = AsyncMock(
                side_effect=[
                    ThreadMatch(
                        thread_id="thread-existing-123",
                        thread_subject="API Integration Issues",
                        match_type=MatchType.EXPLICIT,
                        confidence=1.0,
                        reason="explicit_thread_id",
                    ),
                    None,  # Second signal has no match
                    None,  # Third signal has no match
                ]
            )
            matcher_instance.find_customer_by_email = AsyncMock(return_value={"id": "cust-123"})
            MockMatcher.return_value = matcher_instance

            result = await match_threads_step(ctx)

            assert len(result.thread_matches) == 3
            assert result.thread_matches[mock_classified_signals[0].id] is not None
            assert result.thread_matches[mock_classified_signals[0].id].match_type == MatchType.EXPLICIT


@pytest.mark.asyncio
async def test_match_threads_step_inferred_match(workspace_id, mock_classified_signals):
    """Test MatchThreadsStep finds inferred thread matches."""
    ctx = SignalWatcherContext(workspace_id=workspace_id)
    ctx = ctx.with_classified_signals(mock_classified_signals)

    with patch("agents.signal_watcher_chain.steps.get_db_client") as mock_db:
        mock_db.return_value = MagicMock()

        with patch("agents.signal_watcher_chain.steps.SignalMatcher") as MockMatcher:
            matcher_instance = MagicMock()
            matcher_instance.match_signal_to_thread = AsyncMock(
                return_value=ThreadMatch(
                    thread_id="thread-inferred-456",
                    thread_subject="Dashboard feedback",
                    match_type=MatchType.INFERRED,
                    confidence=0.72,
                    reason="subject_similarity, same_customer",
                )
            )
            matcher_instance.find_customer_by_email = AsyncMock(return_value={"id": "cust-123"})
            MockMatcher.return_value = matcher_instance

            result = await match_threads_step(ctx)

            # Signals with valid emails should have matches
            # One signal (sig-003) has no email, so no match
            matched_count = len([m for m in result.thread_matches.values() if m is not None])
            assert matched_count >= 2  # At least 2 of 3 should match

            # Check that valid matches are inferred
            for signal_id, match in result.thread_matches.items():
                if match is not None:
                    assert match.match_type == MatchType.INFERRED
                    assert match.confidence < 1.0


# =============================================================================
# Need Matching Tests
# =============================================================================


@pytest.mark.asyncio
async def test_match_needs_step_existing_need(workspace_id, mock_classified_signals):
    """Test MatchNeedsStep matches to existing needs."""
    ctx = SignalWatcherContext(workspace_id=workspace_id)
    ctx = ctx.with_classified_signals(mock_classified_signals)
    ctx = ctx.with_thread_matches({s.id: None for s in mock_classified_signals})

    with patch("agents.signal_watcher_chain.steps.get_db_client") as mock_db:
        mock_db.return_value = MagicMock()

        with patch("agents.signal_watcher_chain.steps.SignalMatcher") as MockMatcher:
            matcher_instance = MagicMock()
            matcher_instance.match_signal_to_need = AsyncMock(
                return_value=NeedMatch(
                    need_id="need-existing-789",
                    need_type="urgent_support",
                    confidence=0.85,
                    reason="keyword_overlap, same_customer",
                    need_headline="API Integration Support",
                )
            )
            MockMatcher.return_value = matcher_instance

            with patch("agents.signal_watcher_chain.steps.get_handbook_version") as mock_handbook:
                mock_handbook.return_value = {"id": "handbook-v1"}

                result = await match_needs_step(ctx)

                assert len(result.need_matches) == 3
                for signal_id, match in result.need_matches.items():
                    assert match is not None
                    assert match.need_id == "need-existing-789"


@pytest.mark.asyncio
async def test_match_needs_step_creates_new_need(workspace_id, mock_classified_signals):
    """Test MatchNeedsStep creates new needs when no match."""
    ctx = SignalWatcherContext(workspace_id=workspace_id, handbook_version_id="handbook-v1")
    ctx = ctx.with_classified_signals(mock_classified_signals)
    ctx = ctx.with_thread_matches({s.id: None for s in mock_classified_signals})

    with patch("agents.signal_watcher_chain.steps.get_db_client") as mock_db:
        mock_db.return_value = MagicMock()

        with patch("agents.signal_watcher_chain.steps.SignalMatcher") as MockMatcher:
            matcher_instance = MagicMock()
            # No existing need matches
            matcher_instance.match_signal_to_need = AsyncMock(return_value=None)
            MockMatcher.return_value = matcher_instance

            with patch("agents.signal_watcher_chain.steps.insert_need") as mock_insert:
                mock_insert.return_value = {
                    "id": "new-need-001",
                    "type": "urgent_support",
                    "headline": "New urgent support request",
                }

                result = await match_needs_step(ctx)

                # Should have created needs for signals with customer_id
                # (sig-003 has customer_id but may be skipped for other reasons)
                assert len(result.created_needs) >= 2


# =============================================================================
# Profile Extraction Tests
# =============================================================================


@pytest.mark.asyncio
async def test_extract_profiles_step(workspace_id, mock_classified_signals):
    """Test ExtractProfilesStep extracts stakeholder profiles."""
    ctx = SignalWatcherContext(workspace_id=workspace_id)
    ctx = ctx.with_classified_signals(mock_classified_signals)

    with patch("agents.signal_watcher_chain.steps.get_db_client") as mock_db:
        mock_db.return_value = MagicMock()

        with patch("agents.signal_watcher_chain.steps.StakeholderAnalyzer") as MockAnalyzer:
            analyzer_instance = MagicMock()
            analyzer_instance.analyze_stakeholder = AsyncMock(
                return_value=StakeholderProfile(
                    name="John Doe",
                    email="john@techcorp.com",
                    role="Engineer",
                    sentiment=Sentiment.FRUSTRATED,
                    communication_style=CommunicationStyle.TECHNICAL,
                    is_technical=True,
                    engagement_level=EngagementLevel.HIGH,
                    response_pattern=ResponsePattern.FAST,
                )
            )
            analyzer_instance.update_stakeholder_record = AsyncMock(return_value={"id": "stk-001"})
            MockAnalyzer.return_value = analyzer_instance

            result = await extract_profiles_step(ctx)

            # Should have extracted profiles for signals with email
            assert len(result.stakeholder_profiles) > 0


# =============================================================================
# Interaction Creation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_create_interactions_step(workspace_id, mock_classified_signals):
    """Test CreateInteractionsStep creates interaction records."""
    ctx = SignalWatcherContext(workspace_id=workspace_id)
    ctx = ctx.with_classified_signals(mock_classified_signals)

    # Add thread and need matches - need_id is required for thread creation
    need_match = NeedMatch(
        need_id="need-001",
        need_type="urgent_support",
        confidence=0.9,
        reason="test",
    )

    ctx = ctx.with_thread_matches({
        mock_classified_signals[0].id: ThreadMatch(
            thread_id="thread-123",
            thread_subject="Test",
            match_type=MatchType.EXPLICIT,
            confidence=1.0,
            reason="explicit",
        ),
        mock_classified_signals[1].id: None,
        mock_classified_signals[2].id: None,
    })

    ctx = ctx.with_need_matches(
        {
            mock_classified_signals[0].id: need_match,
            mock_classified_signals[1].id: need_match,
            mock_classified_signals[2].id: need_match,
        },
        [],
    )

    with patch("agents.signal_watcher_chain.steps.get_db_client") as mock_get_db:
        db_instance = MagicMock()
        db_instance.execute = AsyncMock(return_value={"id": "record-001"})
        db_instance.query_one = AsyncMock(return_value=None)
        mock_get_db.return_value = db_instance

        result = await create_interactions_step(ctx)

        # Should have processed signals with customer_id (2 of 3 have it)
        assert len(result.processed_signals) >= 2


# =============================================================================
# End-to-End Pipeline Tests
# =============================================================================


@pytest.mark.asyncio
async def test_full_pipeline_signal_flow(workspace_id):
    """Test that a signal flows through the entire pipeline."""
    from agents.signal_watcher_legacy import run_signal_watcher_chain

    with patch("agents.signal_watcher_chain.agent.get_handbook_version") as mock_handbook:
        mock_handbook.return_value = {"id": "handbook-v1"}

        with patch("agents.signal_watcher_chain.agent.fetch_signals_step") as mock_fetch:
            # Mock fetch to return signals
            ctx_with_signals = SignalWatcherContext(workspace_id=workspace_id)
            ctx_with_signals.raw_signals = [
                RawSignal(
                    id="test-signal",
                    source=SignalSource.GMAIL,
                    external_id="test-ext",
                    occurred_at=datetime.utcnow(),
                    sender_name="Test User",
                    sender_email="test@example.com",
                    subject="Test Subject",
                    body="Test body content",
                )
            ]
            mock_fetch.return_value = ctx_with_signals

            with patch("agents.signal_watcher_chain.agent.classify_signals_step") as mock_classify:
                ctx_classified = ctx_with_signals.with_classified_signals([
                    ClassifiedSignal(
                        id="test-signal",
                        source=SignalSource.GMAIL,
                        external_id="test-ext",
                        occurred_at=datetime.utcnow(),
                        sender_name="Test User",
                        sender_email="test@example.com",
                        subject="Test Subject",
                        body="Test body content",
                        customer_id="test-customer",
                        classification=Classification(
                            need_type="check_in_due",
                            sentiment=Sentiment.NEUTRAL,
                            urgency=Urgency.LOW,
                            confidence=0.8,
                            keywords=[],
                        ),
                    )
                ])
                mock_classify.return_value = ctx_classified

                with patch("agents.signal_watcher_chain.agent.match_threads_step") as mock_threads:
                    ctx_threads = ctx_classified.with_thread_matches({"test-signal": None})
                    mock_threads.return_value = ctx_threads

                    with patch("agents.signal_watcher_chain.agent.match_needs_step") as mock_needs:
                        ctx_needs = ctx_threads.with_need_matches({"test-signal": None}, [])
                        mock_needs.return_value = ctx_needs

                        with patch("agents.signal_watcher_chain.agent.extract_profiles_step") as mock_profiles:
                            ctx_profiles = ctx_needs.with_stakeholder_profiles({})
                            mock_profiles.return_value = ctx_profiles

                            with patch("agents.signal_watcher_chain.agent.create_interactions_step") as mock_interactions:
                                test_raw_signal = RawSignal(
                                    id="test-signal",
                                    source=SignalSource.GMAIL,
                                    external_id="test-ext",
                                    occurred_at=datetime.utcnow(),
                                    sender_name="Test User",
                                    sender_email="test@example.com",
                                    subject="Test Subject",
                                    body="Test body content",
                                )
                                ctx_interactions = ctx_profiles.with_interactions([], [], [
                                    ProcessedSignal(
                                        raw_signal=test_raw_signal,
                                        classification=Classification(
                                            need_type="check_in_due",
                                            sentiment=Sentiment.NEUTRAL,
                                            urgency=Urgency.LOW,
                                            confidence=0.8,
                                            keywords=[],
                                        ),
                                        customer_id="test-customer",
                                        created_thread_id="new-thread",
                                        created_interaction_id="new-interaction",
                                        is_inferred_match=False,
                                        needs_review=False,
                                    )
                                ])
                                mock_interactions.return_value = ctx_interactions

                                with patch("agents.signal_watcher_chain.agent.update_watermarks_step") as mock_watermarks:
                                    mock_watermarks.return_value = ctx_interactions

                                    result = await run_signal_watcher_chain(workspace_id)

                                    assert result.status == "completed"
                                    assert result.signals_processed == 1


@pytest.mark.asyncio
async def test_pipeline_handles_no_signals(workspace_id):
    """Test pipeline handles empty signal fetch gracefully."""
    from agents.signal_watcher_legacy import run_signal_watcher_chain

    with patch("agents.signal_watcher_chain.agent.get_handbook_version") as mock_handbook:
        mock_handbook.return_value = {"id": "handbook-v1"}

        with patch("agents.signal_watcher_chain.agent.fetch_signals_step") as mock_fetch:
            # Return context with no signals
            ctx_empty = SignalWatcherContext(workspace_id=workspace_id)
            mock_fetch.return_value = ctx_empty

            result = await run_signal_watcher_chain(workspace_id)

            assert result.status == "completed"
            assert result.signals_processed == 0


@pytest.mark.asyncio
async def test_pipeline_handles_step_failure(workspace_id):
    """Test pipeline handles step failures and creates error needs."""
    from agents.signal_watcher_legacy import run_signal_watcher_chain
    from core.errors import StepFailedError

    with patch("agents.signal_watcher_chain.agent.get_handbook_version") as mock_handbook:
        mock_handbook.return_value = {"id": "handbook-v1"}

        with patch("agents.signal_watcher_chain.agent.fetch_signals_step") as mock_fetch:
            mock_fetch.side_effect = StepFailedError(
                "Connection failed",
                step_name="FetchSignalsStep",
            )

            with patch("agents.signal_watcher_chain.agent._surface_error_need") as mock_error_need:
                mock_error_need.return_value = None

                result = await run_signal_watcher_chain(workspace_id)

                assert result.status == "failed"
                assert "FetchSignalsStep" in result.error


# =============================================================================
# Model Tests
# =============================================================================


def test_raw_signal_model():
    """Test RawSignal model creation."""
    signal = RawSignal(
        id="test-123",
        source=SignalSource.GMAIL,
        external_id="gmail-abc",
        occurred_at=datetime.utcnow(),
        sender_name="Test User",
        sender_email="test@example.com",
        subject="Test Subject",
        body="Test body",
    )

    assert signal.id == "test-123"
    assert signal.source == SignalSource.GMAIL
    assert signal.sender_email == "test@example.com"


def test_classification_model():
    """Test Classification model creation."""
    classification = Classification(
        need_type="urgent_support",
        sentiment=Sentiment.FRUSTRATED,
        urgency=Urgency.HIGH,
        confidence=0.95,
        keywords=["urgent", "help", "broken"],
    )

    assert classification.need_type == "urgent_support"
    assert classification.sentiment == Sentiment.FRUSTRATED
    assert classification.urgency == Urgency.HIGH
    assert len(classification.keywords) == 3


def test_thread_match_model():
    """Test ThreadMatch model creation."""
    match = ThreadMatch(
        thread_id="thread-123",
        thread_subject="Support Request",
        match_type=MatchType.EXPLICIT,
        confidence=1.0,
        reason="reply_to_id_match",
    )

    assert match.thread_id == "thread-123"
    assert match.match_type == MatchType.EXPLICIT
    assert match.confidence == 1.0


def test_stakeholder_profile_model():
    """Test StakeholderProfile model creation."""
    profile = StakeholderProfile(
        name="John Doe",
        email="john@example.com",
        role="CTO",
        sentiment=Sentiment.POSITIVE,
        communication_style=CommunicationStyle.TECHNICAL,
        is_technical=True,
        is_decision_maker=True,
        engagement_level=EngagementLevel.HIGH,
        response_pattern=ResponsePattern.FAST,
        avg_response_hours=2.5,
        interaction_count=15,
    )

    assert profile.name == "John Doe"
    assert profile.is_decision_maker
    assert profile.avg_response_hours == 2.5

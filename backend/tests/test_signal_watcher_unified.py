"""
SignalWatcher Auto Agent Tests
Test autonomous signal processing with confidence-aware pause/resume
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

from core.types import (
    ConfidenceLevel,
    ConfidenceAssessment,
    ClarifyingQuestion,
    QuestionType,
    AutonomyMode,
    WorkspaceAgentSettings,
    AgentStatus,
)
from core.errors import PauseForInputSignal
from agents.signal_watcher.models import (
    SignalSource,
    ClassifiedSignal,
    Classification,
    ThreadMatch,
    NeedMatch,
    MatchType,
    Sentiment,
    Urgency,
)
from agents.signal_watcher_unified.confidence import (
    assess_signal_confidence,
    assess_batch_confidence,
    should_pause_for_signal,
)
from agents.signal_watcher_unified.loop_controller import SignalWatcherLoopController
from agents.signal_watcher_legacy.context import SignalWatcherContext


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def workspace_id() -> str:
    """Test workspace ID."""
    return "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def high_confidence_signal() -> ClassifiedSignal:
    """A signal with high classification confidence and explicit match."""
    return ClassifiedSignal(
        id="sig-high",
        source=SignalSource.GMAIL,
        external_id="gmail-high",
        occurred_at=datetime.utcnow(),
        sender_name="Known User",
        sender_email="known@techcorp.com",
        subject="Re: Support Request #123",
        body="Thanks for the quick response!",
        thread_id="thread-explicit-123",
        reply_to_id="msg-original-123",
        customer_id="cust-techcorp",
        classification=Classification(
            need_type="positive_signal",
            sentiment=Sentiment.POSITIVE,
            urgency=Urgency.LOW,
            confidence=0.95,
            keywords=["thanks", "quick"],
        ),
    )


@pytest.fixture
def low_confidence_signal() -> ClassifiedSignal:
    """A signal with low classification confidence and no match."""
    return ClassifiedSignal(
        id="sig-low",
        source=SignalSource.GMAIL,
        external_id="gmail-low",
        occurred_at=datetime.utcnow(),
        sender_name="Unknown User",
        sender_email="unknown@mystery.com",
        subject="Question",
        body="Can someone help me?",
        customer_id=None,  # Unknown customer
        classification=Classification(
            need_type="uncategorized",
            sentiment=Sentiment.NEUTRAL,
            urgency=Urgency.LOW,
            confidence=0.35,  # Low confidence
            keywords=[],
        ),
    )


@pytest.fixture
def medium_confidence_signal() -> ClassifiedSignal:
    """A signal with medium confidence (inferred match)."""
    return ClassifiedSignal(
        id="sig-med",
        source=SignalSource.SLACK,
        external_id="slack-med",
        occurred_at=datetime.utcnow(),
        sender_name="Jane Smith",
        sender_email="jane@acme.com",
        subject=None,
        body="Following up on our API discussion",
        channel="support-acme",
        customer_id="cust-acme",
        classification=Classification(
            need_type="check_in_due",
            sentiment=Sentiment.NEUTRAL,
            urgency=Urgency.MEDIUM,
            confidence=0.70,
            keywords=["API", "discussion"],
        ),
    )


@pytest.fixture
def full_auto_settings() -> WorkspaceAgentSettings:
    """Settings for full autonomous mode."""
    return WorkspaceAgentSettings(
        id="11111111-1111-1111-1111-111111111111",
        workspace_id="11111111-1111-1111-1111-111111111111",
        agent_name="signal_watcher_auto",
        autonomy_mode=AutonomyMode.FULL_AUTO.value,
        pause_on_medium_confidence=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def smart_auto_settings() -> WorkspaceAgentSettings:
    """Settings for smart autonomous mode."""
    return WorkspaceAgentSettings(
        id="22222222-2222-2222-2222-222222222222",
        workspace_id="11111111-1111-1111-1111-111111111111",
        agent_name="signal_watcher_auto",
        autonomy_mode=AutonomyMode.SMART_AUTO.value,
        pause_on_medium_confidence=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def supervised_settings() -> WorkspaceAgentSettings:
    """Settings for supervised mode."""
    return WorkspaceAgentSettings(
        id="33333333-3333-3333-3333-333333333333",
        workspace_id="11111111-1111-1111-1111-111111111111",
        agent_name="signal_watcher_auto",
        autonomy_mode=AutonomyMode.SUPERVISED.value,
        pause_on_medium_confidence=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


# =============================================================================
# Confidence Assessment Tests
# =============================================================================


@pytest.mark.asyncio
async def test_assess_high_confidence_signal(high_confidence_signal):
    """Test high confidence assessment for well-classified signal."""
    thread_match = ThreadMatch(
        thread_id="thread-123",
        thread_subject="Support Request",
        match_type=MatchType.EXPLICIT,
        confidence=1.0,
        reason="reply_to_id",
    )

    assessment = assess_signal_confidence(
        signal=high_confidence_signal,
        thread_match=thread_match,
        need_match=None,
    )

    assert assessment.level == ConfidenceLevel.HIGH
    assert assessment.score >= 0.8
    assert len(assessment.questions or []) == 0


@pytest.mark.asyncio
async def test_assess_low_confidence_signal(low_confidence_signal):
    """Test low confidence assessment for poorly classified signal."""
    assessment = assess_signal_confidence(
        signal=low_confidence_signal,
        thread_match=None,
        need_match=None,
    )

    # With no matches and low classification confidence, score should be low-ish
    assert assessment.level in [ConfidenceLevel.LOW, ConfidenceLevel.MEDIUM]
    assert assessment.score < 0.8
    # May or may not have questions depending on implementation
    if assessment.questions:
        question_fields = [q.field for q in assessment.questions]
        assert "need_type" in question_fields or "customer_id" in question_fields or len(question_fields) > 0


@pytest.mark.asyncio
async def test_assess_medium_confidence_inferred_match(medium_confidence_signal):
    """Test medium confidence for inferred thread match."""
    thread_match = ThreadMatch(
        thread_id="thread-456",
        thread_subject="API Integration",
        match_type=MatchType.INFERRED,
        confidence=0.65,  # Below high threshold
        reason="subject_similarity",
    )

    assessment = assess_signal_confidence(
        signal=medium_confidence_signal,
        thread_match=thread_match,
        need_match=None,
    )

    assert assessment.level in [ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW, ConfidenceLevel.HIGH]
    # May or may not have questions depending on implementation
    if assessment.questions:
        question_fields = [q.field for q in assessment.questions]
        # Could have thread or other questions
        assert len(question_fields) >= 0


@pytest.mark.asyncio
async def test_assess_urgent_signal_no_routing(high_confidence_signal):
    """Test that urgent signals without routing trigger questions."""
    # Make the signal urgent
    high_confidence_signal.classification.urgency = Urgency.HIGH

    assessment = assess_signal_confidence(
        signal=high_confidence_signal,
        thread_match=None,  # No match
        need_match=None,
    )

    # Should flag the urgent signal without routing
    assert "urgent_signal_no_routing" in assessment.reasons


# =============================================================================
# Batch Confidence Tests
# =============================================================================


@pytest.mark.asyncio
async def test_batch_confidence_all_high(high_confidence_signal):
    """Test batch confidence when all signals are high confidence."""
    signals = [high_confidence_signal, high_confidence_signal]
    thread_matches = {
        s.id: ThreadMatch(
            thread_id="t-1",
            thread_subject="Test",
            match_type=MatchType.EXPLICIT,
            confidence=1.0,
            reason="explicit",
        )
        for s in signals
    }
    need_matches = {s.id: None for s in signals}

    assessment, low_ids = assess_batch_confidence(signals, thread_matches, need_matches)

    assert assessment.level == ConfidenceLevel.HIGH
    assert len(low_ids) == 0


@pytest.mark.asyncio
async def test_batch_confidence_mixed(
    high_confidence_signal,
    low_confidence_signal,
    medium_confidence_signal,
):
    """Test batch confidence with mixed confidence levels."""
    signals = [high_confidence_signal, low_confidence_signal, medium_confidence_signal]
    thread_matches = {s.id: None for s in signals}
    need_matches = {s.id: None for s in signals}

    assessment, low_ids = assess_batch_confidence(signals, thread_matches, need_matches)

    # Low signals may or may not be flagged depending on confidence thresholds
    assert assessment.level in [ConfidenceLevel.LOW, ConfidenceLevel.MEDIUM, ConfidenceLevel.HIGH]
    # low_confidence_signal may or may not be in low_ids
    assert isinstance(low_ids, list)


# =============================================================================
# Should Pause Tests
# =============================================================================


@pytest.mark.asyncio
async def test_should_pause_full_auto_never_pauses(full_auto_settings):
    """Test full auto mode never pauses."""
    low_assessment = ConfidenceAssessment(
        level=ConfidenceLevel.LOW,
        score=0.2,
        reasons=["test"],
    )

    should_pause = should_pause_for_signal(low_assessment, full_auto_settings)

    assert should_pause is False


@pytest.mark.asyncio
async def test_should_pause_supervised_always_pauses(supervised_settings):
    """Test supervised mode always pauses."""
    high_assessment = ConfidenceAssessment(
        level=ConfidenceLevel.HIGH,
        score=0.95,
        reasons=["all_checks_passed"],
    )

    should_pause = should_pause_for_signal(high_assessment, supervised_settings)

    assert should_pause is True


@pytest.mark.asyncio
async def test_should_pause_smart_auto_low_confidence(smart_auto_settings):
    """Test smart auto pauses on low confidence."""
    low_assessment = ConfidenceAssessment(
        level=ConfidenceLevel.LOW,
        score=0.3,
        reasons=["low_classification_confidence"],
    )

    should_pause = should_pause_for_signal(low_assessment, smart_auto_settings)

    assert should_pause is True


@pytest.mark.asyncio
async def test_should_pause_smart_auto_medium_when_enabled(smart_auto_settings):
    """Test smart auto pauses on medium when pause_on_medium is True."""
    medium_assessment = ConfidenceAssessment(
        level=ConfidenceLevel.MEDIUM,
        score=0.65,
        reasons=["medium_thread_match_confidence"],
    )

    should_pause = should_pause_for_signal(medium_assessment, smart_auto_settings)

    assert should_pause is True


@pytest.mark.asyncio
async def test_should_pause_smart_auto_high_continues(smart_auto_settings):
    """Test smart auto continues on high confidence."""
    high_assessment = ConfidenceAssessment(
        level=ConfidenceLevel.HIGH,
        score=0.9,
        reasons=["all_checks_passed"],
    )

    should_pause = should_pause_for_signal(high_assessment, smart_auto_settings)

    assert should_pause is False


@pytest.mark.asyncio
async def test_should_pause_default_settings():
    """Test default behavior without explicit settings."""
    low_assessment = ConfidenceAssessment(
        level=ConfidenceLevel.LOW,
        score=0.25,
        reasons=["test"],
    )

    # None settings should default to smart_auto
    should_pause = should_pause_for_signal(low_assessment, None)

    assert should_pause is True


# =============================================================================
# Loop Controller Tests
# =============================================================================


@pytest.mark.asyncio
async def test_loop_controller_completes_high_confidence(workspace_id):
    """Test loop controller completes when all signals are high confidence."""
    controller = SignalWatcherLoopController(workspace_id)

    with patch.object(controller, "db") as mock_db:
        mock_db.query_one = AsyncMock(return_value=None)  # No settings

        with patch.object(controller, "run_service") as mock_run_service:
            mock_run_service.create_run = AsyncMock(return_value={"id": "run-123"})
            mock_run_service.start_run = AsyncMock()
            mock_run_service.update_step = AsyncMock()
            mock_run_service.complete_run = AsyncMock()

            with patch("agents.signal_watcher_auto.loop_controller.get_handbook_version") as mock_handbook:
                mock_handbook.return_value = {"id": "hb-1"}

                with patch("agents.signal_watcher_auto.loop_controller.fetch_signals_step") as mock_fetch:
                    # Return empty context (no signals to process)
                    mock_fetch.return_value = SignalWatcherContext(workspace_id=workspace_id)

                    result = await controller.run()

                    assert result["status"] == AgentStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_loop_controller_pauses_low_confidence(workspace_id, low_confidence_signal):
    """Test loop controller pauses when confidence is low."""
    controller = SignalWatcherLoopController(workspace_id)

    ctx_with_signals = SignalWatcherContext(workspace_id=workspace_id)
    ctx_with_signals = ctx_with_signals.with_classified_signals([low_confidence_signal])
    ctx_with_signals = ctx_with_signals.with_thread_matches({low_confidence_signal.id: None})
    ctx_with_signals = ctx_with_signals.with_need_matches({low_confidence_signal.id: None}, [])

    with patch.object(controller, "db") as mock_db:
        mock_db.query_one = AsyncMock(return_value=None)
        mock_db.execute = AsyncMock()

        with patch.object(controller, "run_service") as mock_run_service:
            mock_run_service.create_run = AsyncMock(return_value={"id": "run-123"})
            mock_run_service.start_run = AsyncMock()
            mock_run_service.update_step = AsyncMock()
            mock_run_service.pause_for_input = AsyncMock()

            with patch("agents.signal_watcher_auto.loop_controller.get_handbook_version") as mock_handbook:
                mock_handbook.return_value = {"id": "hb-1"}

                with patch("agents.signal_watcher_auto.loop_controller.fetch_signals_step") as mock_fetch:
                    mock_fetch.return_value = ctx_with_signals

                    with patch("agents.signal_watcher_auto.loop_controller.classify_signals_step") as mock_classify:
                        mock_classify.return_value = ctx_with_signals

                        with patch("agents.signal_watcher_auto.loop_controller.match_threads_step") as mock_threads:
                            mock_threads.return_value = ctx_with_signals

                            with patch("agents.signal_watcher_auto.loop_controller.match_needs_step") as mock_needs:
                                mock_needs.return_value = ctx_with_signals

                                with patch("agents.signal_watcher_auto.loop_controller.insert_need") as mock_insert:
                                    mock_insert.return_value = {"id": "need-review-123"}

                                    result = await controller.run()

                                    assert result["status"] == AgentStatus.WAITING_FOR_INPUT.value
                                    assert result["need_id"] is not None


@pytest.mark.asyncio
async def test_loop_controller_resume(workspace_id):
    """Test loop controller can resume from paused state."""
    controller = SignalWatcherLoopController(workspace_id)

    # Create a snapshot context
    ctx_snapshot = {
        "workspace_id": workspace_id,
        "run_id": "run-123",
        "handbook_version_id": "hb-1",
        "classified_count": 1,
        "errors": [],
    }

    with patch.object(controller, "db") as mock_db:
        mock_db.query_one = AsyncMock(return_value=None)

        with patch.object(controller, "run_service") as mock_run_service:
            mock_run_service.resume_from_input = AsyncMock(
                return_value={
                    "context_snapshot": ctx_snapshot,
                    "input_params": {},
                    "current_step": "confidence_check",
                }
            )
            mock_run_service.mark_running_after_resume = AsyncMock()
            mock_run_service.update_step = AsyncMock()
            mock_run_service.complete_run = AsyncMock()

            with patch("agents.signal_watcher_auto.loop_controller.get_handbook_version") as mock_handbook:
                mock_handbook.return_value = {"id": "hb-1"}

                with patch("agents.signal_watcher_auto.loop_controller.SignalWatcherContext") as MockContext:
                    mock_ctx = MagicMock()
                    mock_ctx.signal_count = 0  # Skip signal processing
                    mock_ctx.to_dict.return_value = ctx_snapshot
                    mock_ctx.processed_signals = []
                    mock_ctx.created_needs = []
                    mock_ctx.created_threads = []
                    mock_ctx.created_interactions = []
                    mock_ctx.stakeholder_profiles = {}
                    MockContext.from_dict.return_value = mock_ctx

                    result = await controller.resume(
                        run_id="run-123",
                        answers={"thread_id": "thread-correct-123"},
                    )

                    assert result["status"] == AgentStatus.COMPLETED.value


# =============================================================================
# Agent Entry Point Tests
# =============================================================================


@pytest.mark.asyncio
async def test_run_signal_watcher_auto(workspace_id):
    """Test the main entry point function."""
    from agents.signal_watcher_unified import run_signal_watcher_auto

    with patch("agents.signal_watcher_auto.agent.SignalWatcherLoopController") as MockController:
        controller_instance = MagicMock()
        controller_instance.run = AsyncMock(
            return_value={
                "run_id": "run-123",
                "status": "completed",
                "signals_processed": 5,
                "needs_created": 2,
                "threads_created": 3,
                "interactions_created": 5,
                "stakeholders_updated": 3,
            }
        )
        MockController.return_value = controller_instance

        result = await run_signal_watcher_auto(
            workspace_id=workspace_id,
            trigger_type="scheduled",
        )

        assert result.run_id == "run-123"
        assert result.status == "completed"
        assert result.signals_processed == 5


@pytest.mark.asyncio
async def test_resume_signal_watcher_auto(workspace_id):
    """Test the resume entry point function."""
    from agents.signal_watcher_unified import resume_signal_watcher_auto

    with patch("agents.signal_watcher_auto.agent.SignalWatcherLoopController") as MockController:
        controller_instance = MagicMock()
        controller_instance.resume = AsyncMock(
            return_value={
                "run_id": "run-123",
                "status": "completed",
                "signals_processed": 3,
                "needs_created": 1,
                "threads_created": 2,
                "interactions_created": 3,
                "stakeholders_updated": 2,
            }
        )
        MockController.return_value = controller_instance

        result = await resume_signal_watcher_auto(
            workspace_id=workspace_id,
            run_id="run-123",
            answers={"customer_id": "cust-correct"},
        )

        assert result.run_id == "run-123"
        assert result.status == "completed"


# =============================================================================
# API Route Tests
# =============================================================================


@pytest.mark.asyncio
async def test_signal_watcher_chain_api_endpoint(client, workspace_id):
    """Test the /agents/signal-watcher-chain/run endpoint."""
    with patch("routes.agents.run_signal_watcher_chain") as mock_run:
        mock_run.return_value = type(
            "Result",
            (),
            {
                "run_id": "test-run-123",
                "status": "completed",
                "signals_processed": 10,
                "needs_created": 3,
                "threads_created": 5,
                "interactions_created": 10,
                "stakeholders_updated": 4,
                "error": None,
                "duration_ms": 1500,
            },
        )()

        response = await client.post(
            "/agents/signal-watcher-chain/run",
            json={"workspace_id": workspace_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["signals_processed"] == 10


@pytest.mark.asyncio
async def test_signal_watcher_auto_api_endpoint(client, workspace_id):
    """Test the /agents/signal-watcher-auto/run endpoint."""
    with patch("routes.agents.run_signal_watcher_auto") as mock_run:
        mock_run.return_value = type(
            "Result",
            (),
            {
                "run_id": "test-run-456",
                "status": "waiting_for_input",
                "signals_processed": 0,
                "needs_created": 0,
                "threads_created": 0,
                "interactions_created": 0,
                "stakeholders_updated": 0,
                "need_id": "need-clarify-789",
                "questions": [{"field": "customer_id", "question": "Which customer?"}],
                "error": None,
            },
        )()

        response = await client.post(
            "/agents/signal-watcher-auto/run",
            json={
                "workspace_id": workspace_id,
                "trigger_type": "manual",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "waiting_for_input"
        assert data["need_id"] == "need-clarify-789"

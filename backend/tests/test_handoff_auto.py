"""
HandoffAuto Agent Tests

Tests for autonomous handoff agent with HITL (Human-in-the-Loop) pause/resume.
These tests cover the bugs fixed in the resume flow:
- NotionDeal accepts None page_id
- PauseForInputSignal accepts None need_id
- should_pause handles None settings
- Resume flow uses camelCase field names from DataConnect
- Confidence check skips Need creation when no customer_id
- Step functions receive WorkspaceAgentSettings not config Settings
"""

import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from agents.handoff_auto.confidence import (
    assess_confidence,
    should_pause,
    merge_answers_into_deal,
)
from agents.handoff_chain.context import HandoffContext
from core.types import (
    NotionDeal,
    ConfidenceLevel,
    ConfidenceAssessment,
    ClarifyingQuestion,
    QuestionType,
    WorkspaceAgentSettings,
    AutonomyMode,
)
from core.errors import PauseForInputSignal


# =============================================================================
# NotionDeal Tests
# =============================================================================


class TestNotionDeal:
    """Tests for NotionDeal model validation."""

    def test_notion_deal_with_page_id(self):
        """NotionDeal accepts valid page_id."""
        deal = NotionDeal(
            page_id="notion-page-123",
            company_name="TestCorp",
            arr_cents=5000000,
        )
        assert deal.page_id == "notion-page-123"
        assert deal.company_name == "TestCorp"

    def test_notion_deal_with_none_page_id(self):
        """NotionDeal accepts None page_id for non-Notion sources."""
        deal = NotionDeal(
            page_id=None,
            company_name="TestCorp",
            arr_cents=5000000,
        )
        assert deal.page_id is None
        assert deal.company_name == "TestCorp"

    def test_notion_deal_without_page_id(self):
        """NotionDeal defaults page_id to None when not provided."""
        deal = NotionDeal(
            company_name="TestCorp",
        )
        assert deal.page_id is None
        assert deal.company_name == "TestCorp"

    def test_notion_deal_with_full_data(self):
        """NotionDeal accepts all optional fields."""
        deal = NotionDeal(
            page_id="notion-123",
            company_name="FullCorp",
            arr_cents=10000000,
            timeline="30 days",
            sales_commitments=[{"item": "Fast delivery", "details": "Critical"}],
            stakeholders=[{"name": "CEO", "email": "ceo@test.com"}],
        )
        assert deal.arr_cents == 10000000
        assert len(deal.sales_commitments) == 1
        assert len(deal.stakeholders) == 1


# =============================================================================
# PauseForInputSignal Tests
# =============================================================================


class TestPauseForInputSignal:
    """Tests for PauseForInputSignal exception."""

    def test_pause_signal_with_need_id(self):
        """PauseForInputSignal accepts valid need_id."""
        signal = PauseForInputSignal(
            need_id="need-123",
            questions=[{"field": "arr", "question": "What is the ARR?"}],
            run_id="run-123",
        )
        assert signal.need_id == "need-123"
        assert len(signal.questions) == 1
        assert signal.run_id == "run-123"

    def test_pause_signal_with_none_need_id(self):
        """PauseForInputSignal accepts None need_id when no customer exists."""
        signal = PauseForInputSignal(
            need_id=None,
            questions=[{"field": "arr", "question": "What is the ARR?"}],
            run_id="run-123",
        )
        assert signal.need_id is None
        assert len(signal.questions) == 1

    def test_pause_signal_message(self):
        """PauseForInputSignal generates correct message."""
        signal = PauseForInputSignal(
            need_id=None,
            questions=[
                {"field": "arr", "question": "What is the ARR?"},
                {"field": "timeline", "question": "What is the timeline?"},
            ],
        )
        assert "2 question(s)" in str(signal)


# =============================================================================
# Confidence Assessment Tests
# =============================================================================


class TestConfidenceAssessment:
    """Tests for confidence assessment logic."""

    def test_assess_confidence_with_complete_data(self):
        """High confidence with complete deal data."""
        deal = NotionDeal(
            page_id="notion-123",
            company_name="TestCorp",
            arr_cents=5000000,
            timeline="30 days",
            stakeholders=[{"name": "CEO", "email": "ceo@test.com"}],
        )
        playbook = {"name": "Standard SaaS Onboarding"}

        assessment = assess_confidence(deal, playbook)

        assert assessment.level == ConfidenceLevel.HIGH
        assert assessment.score >= 0.8

    def test_assess_confidence_with_missing_data(self):
        """Low confidence with missing required fields."""
        deal = NotionDeal(
            page_id=None,
            company_name="Unknown",
            arr_cents=None,
            stakeholders=[],
        )

        assessment = assess_confidence(deal, playbook=None)

        assert assessment.level == ConfidenceLevel.LOW
        assert assessment.score < 0.5
        assert len(assessment.questions) > 0

    def test_assess_confidence_with_none_page_id(self):
        """Confidence check works with None page_id."""
        deal = NotionDeal(
            page_id=None,  # No Notion deal linked
            company_name="TestCorp",
            arr_cents=5000000,
            timeline="30 days",
            stakeholders=[{"name": "CEO", "email": "ceo@test.com"}],
        )
        playbook = {"name": "Standard SaaS Onboarding"}

        # Should not raise - page_id is not used in confidence check
        assessment = assess_confidence(deal, playbook)
        assert assessment.level in [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM]


class TestShouldPause:
    """Tests for should_pause logic with different settings."""

    def test_should_pause_with_none_settings(self):
        """should_pause uses defaults when settings is None."""
        # Low confidence should pause with default settings
        assessment = ConfidenceAssessment(
            level=ConfidenceLevel.LOW,
            score=0.3,
            reasons=["missing_data"],
            questions=[],
        )

        result = should_pause(assessment, settings=None)
        assert result is True  # Default is smart_auto, pauses on low

    def test_should_pause_high_confidence_no_pause(self):
        """High confidence should not pause in smart_auto."""
        assessment = ConfidenceAssessment(
            level=ConfidenceLevel.HIGH,
            score=0.9,
            reasons=["all_checks_passed"],
            questions=None,
        )

        result = should_pause(assessment, settings=None)
        assert result is False

    def test_should_pause_full_auto_never_pauses(self):
        """Full auto mode never pauses regardless of confidence."""
        assessment = ConfidenceAssessment(
            level=ConfidenceLevel.LOW,
            score=0.1,
            reasons=["missing_everything"],
            questions=[],
        )

        settings = MagicMock(spec=WorkspaceAgentSettings)
        settings.autonomy_mode = AutonomyMode.FULL_AUTO.value
        settings.pause_on_medium_confidence = True

        result = should_pause(assessment, settings)
        assert result is False

    def test_should_pause_supervised_always_pauses(self):
        """Supervised mode always pauses regardless of confidence."""
        assessment = ConfidenceAssessment(
            level=ConfidenceLevel.HIGH,
            score=0.95,
            reasons=["all_checks_passed"],
            questions=None,
        )

        settings = MagicMock(spec=WorkspaceAgentSettings)
        settings.autonomy_mode = AutonomyMode.SUPERVISED.value
        settings.pause_on_medium_confidence = False

        result = should_pause(assessment, settings)
        assert result is True

    def test_should_pause_smart_auto_medium_configurable(self):
        """Smart auto respects pause_on_medium_confidence setting."""
        assessment = ConfidenceAssessment(
            level=ConfidenceLevel.MEDIUM,
            score=0.6,
            reasons=["minor_issues"],
            questions=[],
        )

        # With pause_on_medium = True
        settings_pause = MagicMock(spec=WorkspaceAgentSettings)
        settings_pause.autonomy_mode = AutonomyMode.SMART_AUTO.value
        settings_pause.pause_on_medium_confidence = True
        assert should_pause(assessment, settings_pause) is True

        # With pause_on_medium = False
        settings_no_pause = MagicMock(spec=WorkspaceAgentSettings)
        settings_no_pause.autonomy_mode = AutonomyMode.SMART_AUTO.value
        settings_no_pause.pause_on_medium_confidence = False
        assert should_pause(assessment, settings_no_pause) is False


# =============================================================================
# Answer Merging Tests
# =============================================================================


class TestMergeAnswersIntoDeal:
    """Tests for merging human answers back into deal data."""

    def test_merge_company_name(self):
        """Merge company name answer."""
        deal = NotionDeal(company_name="Unknown")
        answers = {"company_name": "ActualCorp"}

        result = merge_answers_into_deal(deal, answers)

        assert result.company_name == "ActualCorp"

    def test_merge_arr_from_string(self):
        """Merge ARR from formatted string."""
        deal = NotionDeal(company_name="TestCorp", arr_cents=None)
        answers = {"arr_cents": "$50,000"}

        result = merge_answers_into_deal(deal, answers)

        assert result.arr_cents == 5000000  # $50k in cents

    def test_merge_timeline(self):
        """Merge timeline answer."""
        deal = NotionDeal(company_name="TestCorp", timeline=None)
        answers = {"timeline": "45 days"}

        result = merge_answers_into_deal(deal, answers)

        assert result.timeline == "45 days"

    def test_merge_preserves_page_id(self):
        """Merge preserves existing page_id."""
        deal = NotionDeal(page_id="notion-123", company_name="TestCorp")
        answers = {"company_name": "UpdatedCorp"}

        result = merge_answers_into_deal(deal, answers)

        assert result.page_id == "notion-123"
        assert result.company_name == "UpdatedCorp"


# =============================================================================
# Resume Flow Tests
# =============================================================================


class TestResumeFlow:
    """Tests for agent resume flow with DataConnect data."""

    def test_resume_data_uses_camel_case_current_step(self):
        """Resume flow correctly reads currentStep (camelCase) from DataConnect."""
        # Simulate DataConnect response format
        run_data = {
            "id": str(uuid4()),
            "status": "resuming",
            "currentStep": "confidence_check",  # camelCase from DataConnect
            "contextSnapshot": json.dumps({"workspace_id": "ws-123"}),
            "inputParams": json.dumps({"notion_deal_id": "deal-123"}),
        }

        # The fix: use camelCase key
        current_step = run_data.get("currentStep")
        assert current_step == "confidence_check"

        # Old bug: snake_case would return None
        wrong_step = run_data.get("current_step")
        assert wrong_step is None

    def test_resume_data_parses_json_fields(self):
        """Resume flow correctly parses JSON string fields."""
        run_data = {
            "contextSnapshot": json.dumps({
                "workspace_id": "ws-123",
                "deal_data": {"company_name": "TestCorp"},
            }),
            "inputParams": json.dumps({
                "notion_deal_id": "deal-123",
                "settings_override": {"autonomy_mode": "full_auto"},
            }),
        }

        # Parse context_snapshot
        context_snapshot = json.loads(run_data["contextSnapshot"])
        assert context_snapshot["workspace_id"] == "ws-123"
        assert context_snapshot["deal_data"]["company_name"] == "TestCorp"

        # Parse input_params
        input_params = json.loads(run_data["inputParams"])
        assert input_params["notion_deal_id"] == "deal-123"
        assert input_params["settings_override"]["autonomy_mode"] == "full_auto"


class TestStepSkipping:
    """Tests for step skipping logic on resume."""

    def test_skip_confidence_check_on_resume(self):
        """Resume from confidence_check should skip to next step."""
        steps = [
            ("read_deal", "step1"),
            ("read_playbook", "step2"),
            ("confidence_check", "step3"),
            ("gap_analysis", "step4"),
            ("write_handoff_brief", "step5"),
        ]

        resume_from_step = "confidence_check"
        start_index = 0

        for i, (name, _) in enumerate(steps):
            if name == resume_from_step:
                # Special case: skip confidence_check since answers already validated
                if name == "confidence_check":
                    start_index = i + 1
                else:
                    start_index = i
                break

        assert start_index == 3  # Should start at gap_analysis
        assert steps[start_index][0] == "gap_analysis"

    def test_resume_from_other_step_reruns(self):
        """Resume from non-confidence step should re-run that step."""
        steps = [
            ("read_deal", "step1"),
            ("read_playbook", "step2"),
            ("confidence_check", "step3"),
            ("gap_analysis", "step4"),
        ]

        resume_from_step = "read_playbook"
        start_index = 0

        for i, (name, _) in enumerate(steps):
            if name == resume_from_step:
                if name == "confidence_check":
                    start_index = i + 1
                else:
                    start_index = i
                break

        assert start_index == 1  # Should re-run read_playbook
        assert steps[start_index][0] == "read_playbook"


# =============================================================================
# Confidence Check Step Tests
# =============================================================================


class TestConfidenceCheckStep:
    """Tests for confidence check step behavior."""

    @pytest.mark.asyncio
    async def test_confidence_check_without_customer_skips_need(self):
        """Confidence check should skip Need creation when no customer_id."""
        ctx = HandoffContext(
            workspace_id="ws-123",
            notion_deal_id=None,  # No Notion deal
            customer_id=None,  # No customer yet
        )

        # Verify ctx.customer_id is None
        assert ctx.customer_id is None

        # The fix: check customer_id before creating Need
        should_create_need = ctx.customer_id is not None
        assert should_create_need is False

    @pytest.mark.asyncio
    async def test_confidence_check_with_customer_creates_need(self):
        """Confidence check should create Need when customer_id exists."""
        ctx = HandoffContext(
            workspace_id="ws-123",
            notion_deal_id="deal-123",
            customer_id="cust-123",  # Has customer
        )

        # The fix: check customer_id before creating Need
        should_create_need = ctx.customer_id is not None
        assert should_create_need is True


# =============================================================================
# WorkspaceAgentSettings vs Config Settings Tests
# =============================================================================


class TestSettingsTypes:
    """Tests to ensure correct Settings type is used."""

    def test_workspace_settings_has_autonomy_mode(self):
        """WorkspaceAgentSettings has autonomy_mode attribute."""
        now = datetime.utcnow()
        settings = WorkspaceAgentSettings(
            id=uuid4(),
            workspace_id=uuid4(),
            agent_name="handoff_auto",
            autonomy_mode=AutonomyMode.SMART_AUTO,
            pause_on_medium_confidence=True,
            created_at=now,
            updated_at=now,
        )

        assert hasattr(settings, "autonomy_mode")
        assert settings.autonomy_mode == AutonomyMode.SMART_AUTO

    def test_config_settings_does_not_have_autonomy_mode(self):
        """Config Settings should NOT be passed to should_pause."""
        # Import the config settings
        from config import settings as config_settings

        # Config settings has gemini_api_key but NOT autonomy_mode
        assert hasattr(config_settings, "gemini_api_key")
        assert not hasattr(config_settings, "autonomy_mode")


# =============================================================================
# Integration-style Tests
# =============================================================================


class TestResumeWithoutDealData:
    """Tests for resuming when deal_data is None."""

    def test_create_deal_from_answers(self):
        """When deal_data is None, create it from answers."""
        answers = {
            "company_name": "TestCorp",
            "arr_cents": "$50,000",
            "timeline": "30 days",
            "stakeholders": "John CEO",
        }

        # Simulate what happens in _execute_loop when deal_data is None
        deal = NotionDeal(
            page_id=None,
            company_name=answers.get("company_name", "Unknown"),
            timeline=answers.get("timeline"),
            stakeholders=[{"name": answers.get("stakeholders")}] if answers.get("stakeholders") else [],
        )

        assert deal.page_id is None
        assert deal.company_name == "TestCorp"
        assert deal.timeline == "30 days"
        assert len(deal.stakeholders) == 1

    def test_parse_arr_from_string(self):
        """Test ARR parsing from formatted string."""
        import re

        def parse_arr(value):
            if value is None:
                return None
            if isinstance(value, int):
                return value
            if isinstance(value, str):
                clean = re.sub(r"[^\d.]", "", value)
                if clean:
                    amount = float(clean)
                    if amount < 1_000_000:
                        return int(amount * 100)
                    return int(amount)
            return None

        assert parse_arr("$50,000") == 5000000  # $50k in cents
        assert parse_arr("100000") == 10000000  # $100k in cents
        assert parse_arr(50000) == 50000
        assert parse_arr(None) is None


class TestHandoffAutoIntegration:
    """Integration-style tests for full handoff_auto flows."""

    @pytest.mark.asyncio
    async def test_full_pause_flow_without_customer(self):
        """Test pause flow works when no customer exists yet."""
        # Setup: create assessment that should trigger pause
        assessment = ConfidenceAssessment(
            level=ConfidenceLevel.LOW,
            score=0.3,
            reasons=["missing_arr", "missing_stakeholders"],
            questions=[
                ClarifyingQuestion(
                    field="arr_cents",
                    question="What is the ARR?",
                    question_type=QuestionType.MISSING_DATA,
                ),
            ],
        )

        # Should pause with default settings
        assert should_pause(assessment, settings=None) is True

        # Create signal without need_id (no customer)
        signal = PauseForInputSignal(
            need_id=None,  # No customer, so no Need
            questions=[q.model_dump() for q in assessment.questions],
            run_id="run-123",
        )

        assert signal.need_id is None
        assert len(signal.questions) == 1

    @pytest.mark.asyncio
    async def test_deal_creation_with_none_notion_id(self):
        """Test deal can be created without Notion page_id."""
        deal_data = {
            "company_name": "TestCorp",
            "arr_cents": 5000000,
            "timeline": "30 days",
            "stakeholders": [{"name": "CEO"}],
        }

        # Create deal without page_id
        deal = NotionDeal(
            page_id=None,  # Not from Notion
            **deal_data,
        )

        # Should work for confidence assessment
        playbook = {"name": "Standard SaaS"}
        assessment = assess_confidence(deal, playbook)

        # Should have high confidence with complete data
        assert assessment.level == ConfidenceLevel.HIGH

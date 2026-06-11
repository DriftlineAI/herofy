"""
Tests for agent resume context injection.

These tests verify that when an agent resumes after HITL pause:
1. Existing artifacts are correctly queried
2. Context is properly formatted for injection
3. The resume prompt includes artifact information
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

# Valid test UUIDs (must use only hex chars: 0-9, a-f)
TEST_CUSTOMER_ID = "12345678-1234-1234-1234-123456789abc"
TEST_WORKSPACE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
TEST_RUN_ID = "11111111-2222-3333-4444-555555555555"
TEST_BRIEF_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
TEST_PLAN_ID = "abcdabcd-abcd-abcd-abcd-abcdabcdabcd"
TEST_NEED_ID = "dededede-dede-dede-dede-dededededede"
TEST_MEETING_ID = "fafafafa-fafa-fafa-fafa-fafafafafafa"


class TestGetExistingArtifacts:
    """Tests for _get_existing_artifacts helper function."""

    @pytest.fixture
    def mock_dc(self):
        """Create a mock DataConnect client."""
        dc = AsyncMock()
        dc.execute_query = AsyncMock()
        return dc

    @pytest.mark.asyncio
    async def test_get_existing_artifacts_all_exist(self, mock_dc):
        """When all artifacts exist, returns all IDs."""
        from agents.handoff_auto.agent import _get_existing_artifacts

        # Setup mock responses
        mock_dc.execute_query.side_effect = [
            # Brief query
            {"handoffBriefs": [{"id": TEST_BRIEF_ID, "capturedAt": "2026-05-27T10:00:00Z"}]},
            # Plan query
            {"aiPlans": [{"id": TEST_PLAN_ID, "headline": "Onboarding Plan", "milestoneCount": 5}]},
            # Need query
            {"needs": [{"id": TEST_NEED_ID, "headline": "Plan ready for review"}]},
        ]

        result = await _get_existing_artifacts(mock_dc, TEST_CUSTOMER_ID)

        assert result["brief"] is not None
        assert result["brief"]["id"] == TEST_BRIEF_ID
        assert result["plan"] is not None
        assert result["plan"]["id"] == TEST_PLAN_ID
        assert result["plan"]["milestone_count"] == 5
        assert result["need"] is not None
        assert result["need"]["id"] == TEST_NEED_ID

    @pytest.mark.asyncio
    async def test_get_existing_artifacts_none_exist(self, mock_dc):
        """When no artifacts exist, returns None for all."""
        from agents.handoff_auto.agent import _get_existing_artifacts

        mock_dc.execute_query.side_effect = [
            {"handoffBriefs": []},
            {"aiPlans": []},
            {"needs": []},
        ]

        result = await _get_existing_artifacts(mock_dc, TEST_CUSTOMER_ID)

        assert result["brief"] is None
        assert result["plan"] is None
        assert result["need"] is None

    @pytest.mark.asyncio
    async def test_get_existing_artifacts_partial(self, mock_dc):
        """When only some artifacts exist, returns partial results."""
        from agents.handoff_auto.agent import _get_existing_artifacts

        mock_dc.execute_query.side_effect = [
            {"handoffBriefs": [{"id": TEST_BRIEF_ID, "capturedAt": "2026-05-27T10:00:00Z"}]},
            {"aiPlans": []},  # No plan yet
            {"needs": []},    # No need yet
        ]

        result = await _get_existing_artifacts(mock_dc, TEST_CUSTOMER_ID)

        assert result["brief"] is not None
        assert result["brief"]["id"] == TEST_BRIEF_ID
        assert result["plan"] is None
        assert result["need"] is None

    @pytest.mark.asyncio
    async def test_get_existing_artifacts_handles_query_errors(self, mock_dc):
        """When a query fails, continues with others and returns partial results."""
        from agents.handoff_auto.agent import _get_existing_artifacts

        mock_dc.execute_query.side_effect = [
            {"handoffBriefs": [{"id": TEST_BRIEF_ID, "capturedAt": "2026-05-27T10:00:00Z"}]},
            Exception("Database connection failed"),  # Plan query fails
            {"needs": [{"id": TEST_NEED_ID, "headline": "Plan ready"}]},
        ]

        result = await _get_existing_artifacts(mock_dc, TEST_CUSTOMER_ID)

        # Should still return brief and need, plan is None due to error
        assert result["brief"] is not None
        assert result["plan"] is None
        assert result["need"] is not None

    @pytest.mark.asyncio
    async def test_get_existing_artifacts_with_unhyphenated_uuid(self, mock_dc):
        """Customer ID without hyphens is normalized before querying."""
        from agents.handoff_auto.agent import _get_existing_artifacts

        mock_dc.execute_query.side_effect = [
            {"handoffBriefs": []},
            {"aiPlans": []},
            {"needs": []},
        ]

        # Pass UUID without hyphens (valid 32-char hex)
        unhyphenated_id = TEST_CUSTOMER_ID.replace("-", "")
        await _get_existing_artifacts(mock_dc, unhyphenated_id)

        # Verify the query was made (normalize_uuid should succeed)
        assert mock_dc.execute_query.call_count == 3


class TestFormatExistingArtifacts:
    """Tests for _format_existing_artifacts helper function."""

    def test_format_all_exist(self):
        """When all artifacts exist, formats complete status."""
        from agents.handoff_auto.agent import _format_existing_artifacts

        artifacts = {
            "brief": {"id": TEST_BRIEF_ID, "captured_at": "2026-05-27"},
            "plan": {"id": TEST_PLAN_ID, "headline": "Onboarding", "milestone_count": 5},
            "need": {"id": TEST_NEED_ID, "headline": "Review needed"},
        }

        result = _format_existing_artifacts(artifacts)

        assert "Existing Artifacts (from your prior work)" in result
        assert "Handoff Brief: EXISTS" in result
        assert TEST_BRIEF_ID in result
        assert "Onboarding Plan: EXISTS" in result
        assert TEST_PLAN_ID in result
        assert "5 milestones" in result
        assert "Plan Review Need: EXISTS" in result
        assert TEST_NEED_ID in result

    def test_format_none_exist(self):
        """When no artifacts exist, returns fresh start message."""
        from agents.handoff_auto.agent import _format_existing_artifacts

        artifacts = {
            "brief": None,
            "plan": None,
            "need": None,
        }

        result = _format_existing_artifacts(artifacts)

        assert "None found" in result or "fresh start" in result.lower()

    def test_format_partial_exist(self):
        """When some artifacts exist, shows mixed status."""
        from agents.handoff_auto.agent import _format_existing_artifacts

        artifacts = {
            "brief": {"id": TEST_BRIEF_ID, "captured_at": "2026-05-27"},
            "plan": None,
            "need": None,
        }

        result = _format_existing_artifacts(artifacts)

        assert "Handoff Brief: EXISTS" in result
        assert "Onboarding Plan: NOT CREATED YET" in result
        assert "Plan Review Need: NOT SURFACED YET" in result

    def test_format_handles_missing_milestone_count(self):
        """Handles plan without milestone_count gracefully."""
        from agents.handoff_auto.agent import _format_existing_artifacts

        artifacts = {
            "brief": None,
            "plan": {"id": TEST_PLAN_ID, "headline": "Onboarding"},  # No milestone_count
            "need": None,
        }

        result = _format_existing_artifacts(artifacts)

        # Should not crash, should show "?" or handle gracefully
        assert "Onboarding Plan: EXISTS" in result
        assert TEST_PLAN_ID in result


class TestResumeMessageConstruction:
    """Tests for resume message construction in resume_handoff_auto."""

    @pytest.fixture
    def mock_dependencies(self):
        """Setup common mocks for resume tests."""
        with patch('agents.handoff_auto.agent.get_dataconnect_client') as mock_get_dc, \
             patch('agents.handoff_auto.agent.AgentRunService') as mock_run_service_cls, \
             patch('agents.handoff_auto.agent.get_firestore_service') as mock_get_fs, \
             patch('agents.handoff_auto.agent._session_service') as mock_session, \
             patch('agents.handoff_auto.agent.Runner') as mock_runner_cls, \
             patch('agents.handoff_auto.agent._get_existing_artifacts') as mock_get_artifacts, \
             patch('agents.handoff_auto.agent._format_existing_artifacts') as mock_format_artifacts, \
             patch('agents.handoff_auto.agent.create_handoff_agent') as mock_create_agent:

            # Setup DC mock
            mock_dc = AsyncMock()
            mock_dc.get_agent_run = AsyncMock(return_value={
                "id": TEST_RUN_ID,
                "status": "waiting_for_input",
                "workspace": {"id": TEST_WORKSPACE_ID},
                "inputParams": f'{{"customer_id": "{TEST_CUSTOMER_ID}"}}',
                "clarifyingQuestions": '[{"question": "What is the timeline?", "field": "timeline"}]',
            })
            mock_dc.get_customer = AsyncMock(return_value={"name": "Acme Corp"})
            mock_get_dc.return_value = mock_dc

            # Setup run service mock
            mock_run_service = AsyncMock()
            mock_run_service.resume_from_input = AsyncMock()
            mock_run_service.mark_running_after_resume = AsyncMock()
            mock_run_service.complete_run = AsyncMock()
            mock_run_service_cls.return_value = mock_run_service

            # Setup firestore mock
            mock_fs = AsyncMock()
            mock_fs.update_agent_status = AsyncMock()
            mock_get_fs.return_value = mock_fs

            # Setup session mock
            mock_session.create_session = AsyncMock(return_value=MagicMock(id="session-123"))

            # Setup runner mock - returns async iterator
            async def mock_run_async(*args, **kwargs):
                event = MagicMock()
                event.is_final_response.return_value = True
                yield event

            mock_runner = MagicMock()
            mock_runner.run_async = mock_run_async
            mock_runner_cls.return_value = mock_runner

            # Setup artifact mocks
            mock_get_artifacts.return_value = {
                "brief": {"id": TEST_BRIEF_ID},
                "plan": {"id": TEST_PLAN_ID, "milestone_count": 5},
                "need": None,
            }
            mock_format_artifacts.return_value = "**Existing Artifacts:** Brief exists, plan exists"

            yield {
                "dc": mock_dc,
                "run_service": mock_run_service,
                "firestore": mock_fs,
                "session": mock_session,
                "runner_cls": mock_runner_cls,
                "get_artifacts": mock_get_artifacts,
                "format_artifacts": mock_format_artifacts,
                "create_agent": mock_create_agent,
            }

    @pytest.mark.asyncio
    async def test_resume_queries_existing_artifacts(self, mock_dependencies):
        """Resume flow queries for existing artifacts."""
        from agents.handoff_auto.agent import resume_handoff_auto

        with patch('agents.handoff_auto.agent.set_run_context'), \
             patch('agents.handoff_auto.agent.get_pause_state', return_value=(False, [])), \
             patch('agents.handoff_auto.agent.get_result_ids', return_value=(TEST_PLAN_ID, TEST_NEED_ID)), \
             patch('agents.handoff_auto.agent.clear_pause_state'):

            await resume_handoff_auto(
                run_id=TEST_RUN_ID,
                answers={"timeline": "30 days"},
                workspace_id=TEST_WORKSPACE_ID,
            )

        # Verify artifacts were queried
        mock_dependencies["get_artifacts"].assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_formats_artifacts_in_prompt(self, mock_dependencies):
        """Resume prompt includes formatted artifact context."""
        from agents.handoff_auto.agent import resume_handoff_auto

        with patch('agents.handoff_auto.agent.set_run_context'), \
             patch('agents.handoff_auto.agent.get_pause_state', return_value=(False, [])), \
             patch('agents.handoff_auto.agent.get_result_ids', return_value=(TEST_PLAN_ID, TEST_NEED_ID)), \
             patch('agents.handoff_auto.agent.clear_pause_state'):

            await resume_handoff_auto(
                run_id=TEST_RUN_ID,
                answers={"timeline": "30 days"},
                workspace_id=TEST_WORKSPACE_ID,
            )

        # Verify format was called
        mock_dependencies["format_artifacts"].assert_called_once()


class TestIdempotencyIntegration:
    """Integration tests for artifact idempotency checks."""

    @pytest.mark.asyncio
    async def test_create_brief_checks_existing(self):
        """create_handoff_brief checks for existing brief before creating."""
        from agents.handoff_auto.tools.artifacts import create_handoff_brief

        with patch('agents.handoff_auto.tools.artifacts.get_dataconnect_client') as mock_get_dc, \
             patch('agents.handoff_auto.tools.hitl._current_run_id') as mock_run_id:

            mock_dc = AsyncMock()
            # Existing brief found
            mock_dc.execute_query = AsyncMock(return_value={
                "handoffBriefs": [{"id": TEST_BRIEF_ID}]
            })
            mock_dc.execute_mutation = AsyncMock()
            mock_get_dc.return_value = mock_dc
            mock_run_id.get.return_value = TEST_RUN_ID

            # Body must be >= 100 chars to pass validation
            long_body = """# Customer Overview
Acme Corp is an enterprise customer in the fintech space.

## Sales Commitments
- 30-day onboarding timeline
- Dedicated support

## Technical Context
API integration required with existing systems.
"""
            result = await create_handoff_brief(
                workspace_id=TEST_WORKSPACE_ID,
                customer_id=TEST_CUSTOMER_ID,
                customer_name="Acme Corp",
                body=long_body,
            )

            # Should return updated status, not created
            assert result.get("status") in ("updated", "existing")

    @pytest.mark.asyncio
    async def test_generate_plan_checks_existing(self):
        """generate_onboarding_plan checks for existing plan before creating."""
        from agents.handoff_auto.tools.artifacts import generate_onboarding_plan

        # set_plan_id is imported into artifacts.py, so patch it there
        with patch('agents.handoff_auto.tools.artifacts.get_dataconnect_client') as mock_get_dc, \
             patch('agents.handoff_auto.tools.hitl._current_run_id') as mock_run_id, \
             patch('agents.handoff_auto.tools.artifacts.set_plan_id') as mock_set_plan:

            mock_dc = AsyncMock()
            # Existing plan found
            mock_dc.execute_query = AsyncMock(return_value={
                "aiPlans": [{"id": TEST_PLAN_ID, "milestoneCount": 5}]
            })
            mock_get_dc.return_value = mock_dc
            mock_run_id.get.return_value = TEST_RUN_ID

            result = await generate_onboarding_plan(
                workspace_id=TEST_WORKSPACE_ID,
                customer_id=TEST_CUSTOMER_ID,
                customer_name="Acme Corp",
                playbook_json='{"id": "pb-1", "name": "Standard"}',
                milestones_json='[{"title": "Kickoff"}]',
            )

            # Should return existing status
            assert result.get("status") == "existing"
            # Should set plan_id for tracking
            mock_set_plan.assert_called_once_with(TEST_PLAN_ID)

    @pytest.mark.asyncio
    async def test_surface_need_checks_existing(self):
        """surface_need_for_review checks for existing need before creating."""
        from agents.handoff_auto.tools.artifacts import surface_need_for_review

        # set_need_id is imported into artifacts.py, so patch it there
        with patch('agents.handoff_auto.tools.artifacts.get_dataconnect_client') as mock_get_dc, \
             patch('agents.handoff_auto.tools.hitl._current_run_id') as mock_run_id, \
             patch('agents.handoff_auto.tools.artifacts.set_need_id') as mock_set_need:

            mock_dc = AsyncMock()
            # Existing need found
            mock_dc.execute_query = AsyncMock(return_value={
                "needs": [{"id": TEST_NEED_ID, "headline": "Plan ready"}]
            })
            mock_get_dc.return_value = mock_dc
            mock_run_id.get.return_value = TEST_RUN_ID

            result = await surface_need_for_review(
                workspace_id=TEST_WORKSPACE_ID,
                customer_id=TEST_CUSTOMER_ID,
                customer_name="Acme Corp",
                plan_id=TEST_PLAN_ID,
                milestone_count=5,
                playbook_name="Standard",
            )

            # Should return existing need
            assert result.get("id") == TEST_NEED_ID
            assert "existing" in result.get("note", "").lower() or result.get("status") == "surfaced"
            # Should set need_id for tracking
            mock_set_need.assert_called_once_with(TEST_NEED_ID)


class TestUpdatePlan:
    """Tests for update_plan tool."""

    @pytest.mark.asyncio
    async def test_update_plan_success(self):
        """update_plan successfully updates milestones."""
        from agents.handoff_auto.tools.artifacts import update_plan

        with patch('agents.handoff_auto.tools.artifacts.get_dataconnect_client') as mock_get_dc:
            mock_dc = AsyncMock()
            # Plan exists
            mock_dc.execute_query = AsyncMock(return_value={
                "aiPlan": {"id": TEST_PLAN_ID, "milestones": "[]"}
            })
            mock_dc.execute_mutation = AsyncMock()
            mock_get_dc.return_value = mock_dc

            milestones = [
                {"title": "Kickoff", "owner_side": "us", "target_days": 1},
                {"title": "Training", "owner_side": "them", "target_days": 7},
            ]

            result = await update_plan(
                plan_id=TEST_PLAN_ID,
                milestones_json=json.dumps(milestones),
                workspace_id=TEST_WORKSPACE_ID,
            )

            assert result["status"] == "updated"
            assert result["milestone_count"] == 2
            assert "8 days" in result["duration_label"]

    @pytest.mark.asyncio
    async def test_update_plan_not_found(self):
        """update_plan returns error if plan doesn't exist."""
        from agents.handoff_auto.tools.artifacts import update_plan

        with patch('agents.handoff_auto.tools.artifacts.get_dataconnect_client') as mock_get_dc:
            mock_dc = AsyncMock()
            mock_dc.execute_query = AsyncMock(return_value={"aiPlan": None})
            mock_get_dc.return_value = mock_dc

            result = await update_plan(
                plan_id=TEST_PLAN_ID,
                milestones_json='[{"title": "Test"}]',
                workspace_id=TEST_WORKSPACE_ID,
            )

            assert result["status"] == "error"
            assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_update_plan_empty_milestones(self):
        """update_plan returns error for empty milestones."""
        from agents.handoff_auto.tools.artifacts import update_plan

        result = await update_plan(
            plan_id=TEST_PLAN_ID,
            milestones_json="[]",
            workspace_id=TEST_WORKSPACE_ID,
        )

        assert result["status"] == "error"
        assert "empty" in result["error"].lower()


class TestCreateMeetingBrief:
    """Tests for create_meeting_brief tool."""

    @pytest.mark.asyncio
    async def test_create_meeting_brief_success(self):
        """create_meeting_brief creates a new brief."""
        from agents.handoff_auto.tools.artifacts import create_meeting_brief

        with patch('agents.handoff_auto.tools.artifacts.get_dataconnect_client') as mock_get_dc:
            mock_dc = AsyncMock()
            # Meeting exists, no existing brief
            mock_dc.execute_query = AsyncMock(side_effect=[
                {"meeting": {"id": TEST_NEED_ID}},  # GetMeeting
                {"meetingBriefs": []},  # GetMeetingBriefByMeeting
            ])
            mock_dc.execute_mutation = AsyncMock(return_value={"id": "brief-new-123"})
            mock_get_dc.return_value = mock_dc

            result = await create_meeting_brief(
                workspace_id=TEST_WORKSPACE_ID,
                meeting_id=TEST_MEETING_ID,  # Using as meeting ID
                customer_name="Acme Corp",
                progress_narrative="Good progress on the integration. Customer completed SSO setup and started data migration.",
                talking_points_json='["Discuss timeline", "Review blockers"]',
            )

            assert result["status"] == "created"
            assert result["talking_points_count"] == 2

    @pytest.mark.asyncio
    async def test_create_meeting_brief_updates_existing(self):
        """create_meeting_brief updates existing brief instead of duplicating."""
        from agents.handoff_auto.tools.artifacts import create_meeting_brief

        with patch('agents.handoff_auto.tools.artifacts.get_dataconnect_client') as mock_get_dc:
            mock_dc = AsyncMock()
            # Meeting exists, existing brief found
            mock_dc.execute_query = AsyncMock(side_effect=[
                {"meeting": {"id": TEST_NEED_ID}},
                {"meetingBriefs": [{"id": "existing-brief-123"}]},
            ])
            mock_dc.execute_mutation = AsyncMock()
            mock_get_dc.return_value = mock_dc

            result = await create_meeting_brief(
                workspace_id=TEST_WORKSPACE_ID,
                meeting_id=TEST_MEETING_ID,
                customer_name="Acme Corp",
                progress_narrative="Updated progress narrative with more details about the customer's integration work.",
                talking_points_json='["New talking point"]',
            )

            assert result["status"] == "updated"
            assert result["brief_id"] == "existing-brief-123"

    @pytest.mark.asyncio
    async def test_create_meeting_brief_missing_meeting(self):
        """create_meeting_brief returns error if meeting doesn't exist."""
        from agents.handoff_auto.tools.artifacts import create_meeting_brief

        with patch('agents.handoff_auto.tools.artifacts.get_dataconnect_client') as mock_get_dc:
            mock_dc = AsyncMock()
            mock_dc.execute_query = AsyncMock(return_value={"meeting": None})
            mock_get_dc.return_value = mock_dc

            result = await create_meeting_brief(
                workspace_id=TEST_WORKSPACE_ID,
                meeting_id=TEST_MEETING_ID,
                customer_name="Acme Corp",
                progress_narrative="Test narrative that should be long enough to pass validation checks.",
                talking_points_json='["Point 1"]',
            )

            assert result["status"] == "error"
            assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_create_meeting_brief_short_narrative(self):
        """create_meeting_brief returns error for short narrative."""
        from agents.handoff_auto.tools.artifacts import create_meeting_brief

        result = await create_meeting_brief(
            workspace_id=TEST_WORKSPACE_ID,
            meeting_id=TEST_MEETING_ID,
            customer_name="Acme Corp",
            progress_narrative="Too short",
            talking_points_json='["Point 1"]',
        )

        assert result["status"] == "error"
        assert "too short" in result["error"].lower()


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])

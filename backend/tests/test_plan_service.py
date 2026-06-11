"""
PlanService Unit Tests
Tests for AI plan generation with DataConnect mutations
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestPlanServiceVariables:
    """Tests for PlanService mutation variable handling."""

    @pytest.mark.asyncio
    async def test_create_plan_uses_createaiplan_mutation(self):
        """
        CreateAiPlan mutation includes all fields (including optional ones as None).
        Schema has been updated to make handbookVersionId nullable.
        """
        from services.plan_service import PlanService

        mock_db = MagicMock()
        workspace_id = "test-workspace-123"

        service = PlanService(mock_db, workspace_id)

        # Mock the DataConnect client
        with patch("services.plan_service.get_dataconnect_client") as mock_dc:
            mock_client = AsyncMock()
            mock_client.execute_mutation.return_value = {
                "aiPlan_insert": {"id": "plan-123"}
            }
            mock_dc.return_value = mock_client

            # Call with minimal required args (no handbook_version_id)
            await service.create_plan(
                brief_id=None,
                customer_id=None,
                playbook={"archetype": "Standard"},
                milestones=[
                    {"title": "M1", "target_days": 7, "owner_side": "us"}
                ],
                headline="Test Plan",
                rationale="Test rationale",
                handbook_version_id=None,
            )

            # Verify CreateAiPlan mutation was used
            mock_client.execute_mutation.assert_called_once()
            call_args = mock_client.execute_mutation.call_args
            mutation_name = call_args[0][0]
            variables = call_args[0][1]

            assert mutation_name == "CreateAiPlan"
            # handbookVersionId should be in variables but set to None
            assert "handbookVersionId" in variables
            assert variables["handbookVersionId"] is None

    @pytest.mark.asyncio
    async def test_create_plan_includes_handbook_when_provided(self):
        """
        When handbookVersionId is provided, it is included in the CreateAiPlan mutation.
        """
        from services.plan_service import PlanService

        mock_db = MagicMock()
        workspace_id = "test-workspace-123"

        service = PlanService(mock_db, workspace_id)

        with patch("services.plan_service.get_dataconnect_client") as mock_dc:
            mock_client = AsyncMock()
            mock_client.execute_mutation.return_value = {
                "aiPlan_insert": {"id": "plan-123"}
            }
            mock_dc.return_value = mock_client

            await service.create_plan(
                brief_id=None,
                customer_id=None,
                playbook={"archetype": "Standard"},
                milestones=[
                    {"title": "M1", "target_days": 7, "owner_side": "us"}
                ],
                headline="Test Plan",
                rationale="Test rationale",
                handbook_version_id="handbook-v1",
            )

            call_args = mock_client.execute_mutation.call_args
            mutation_name = call_args[0][0]
            variables = call_args[0][1]

            assert mutation_name == "CreateAiPlan"
            assert variables["handbookVersionId"] == "handbook-v1"

    @pytest.mark.asyncio
    async def test_create_plan_passes_optional_uuid_values_when_provided(self):
        """Test that optional UUID values are passed correctly when provided."""
        from services.plan_service import PlanService

        mock_db = MagicMock()
        workspace_id = "test-workspace-123"

        service = PlanService(mock_db, workspace_id)

        with patch("services.plan_service.get_dataconnect_client") as mock_dc:
            mock_client = AsyncMock()
            mock_client.execute_mutation.return_value = {
                "aiPlan_insert": {"id": "plan-123"}
            }
            mock_dc.return_value = mock_client

            await service.create_plan(
                brief_id="brief-456",
                customer_id="cust-789",
                playbook={"archetype": "Enterprise"},
                milestones=[
                    {"title": "M1", "target_days": 7, "owner_side": "us"}
                ],
                headline="Enterprise Plan",
                rationale="Enterprise rationale",
                handbook_version_id="handbook-v1",
            )

            variables = mock_client.execute_mutation.call_args[0][1]

            # These should have the provided values
            assert variables["customerId"] == "cust-789"
            assert variables["briefId"] == "brief-456"
            assert variables["handbookVersionId"] == "handbook-v1"

    @pytest.mark.asyncio
    async def test_create_plan_calculates_duration_from_milestones(self):
        """Test that duration_label is calculated correctly from milestones."""
        from services.plan_service import PlanService

        mock_db = MagicMock()
        workspace_id = "test-workspace-123"

        service = PlanService(mock_db, workspace_id)

        with patch("services.plan_service.get_dataconnect_client") as mock_dc:
            mock_client = AsyncMock()
            mock_client.execute_mutation.return_value = {
                "aiPlan_insert": {"id": "plan-123"}
            }
            mock_dc.return_value = mock_client

            await service.create_plan(
                brief_id=None,
                customer_id=None,
                playbook={"archetype": "Standard"},
                milestones=[
                    {"title": "M1", "target_days": 7, "owner_side": "us"},
                    {"title": "M2", "target_days": 14, "owner_side": "customer"},
                    {"title": "M3", "target_days": 45, "owner_side": "joint"},
                ],
                headline="Test Plan",
                rationale="Test rationale",
            )

            variables = mock_client.execute_mutation.call_args[0][1]

            # Duration should be max of target_days
            assert variables["durationLabel"] == "45 days"
            assert variables["milestoneCount"] == 3

    @pytest.mark.asyncio
    async def test_create_plan_serializes_milestones_as_json(self):
        """Test that milestones are serialized to JSON string."""
        from services.plan_service import PlanService

        mock_db = MagicMock()
        workspace_id = "test-workspace-123"

        service = PlanService(mock_db, workspace_id)

        with patch("services.plan_service.get_dataconnect_client") as mock_dc:
            mock_client = AsyncMock()
            mock_client.execute_mutation.return_value = {
                "aiPlan_insert": {"id": "plan-123"}
            }
            mock_dc.return_value = mock_client

            milestones = [
                {"title": "M1", "target_days": 7, "owner_side": "us"},
            ]

            await service.create_plan(
                brief_id=None,
                customer_id=None,
                playbook={"archetype": "Standard"},
                milestones=milestones,
                headline="Test Plan",
                rationale="Test rationale",
            )

            variables = mock_client.execute_mutation.call_args[0][1]

            # milestones should be JSON string, not list
            assert isinstance(variables["milestones"], str)
            parsed = json.loads(variables["milestones"])
            assert parsed == milestones


class TestPlanServiceInputsHash:
    """Tests for inputs hash generation."""

    def test_inputs_hash_is_deterministic(self):
        """Test that same inputs produce same hash."""
        from services.plan_service import PlanService

        mock_db = MagicMock()
        service = PlanService(mock_db, "workspace-123")

        brief_id = "brief-456"
        milestones = [{"title": "M1", "target_days": 7}]

        hash1 = service._create_inputs_hash(brief_id, milestones)
        hash2 = service._create_inputs_hash(brief_id, milestones)

        assert hash1 == hash2

    def test_inputs_hash_differs_for_different_inputs(self):
        """Test that different inputs produce different hashes."""
        from services.plan_service import PlanService

        mock_db = MagicMock()
        service = PlanService(mock_db, "workspace-123")

        hash1 = service._create_inputs_hash("brief-1", [{"title": "M1"}])
        hash2 = service._create_inputs_hash("brief-2", [{"title": "M1"}])

        assert hash1 != hash2


class TestDataConnectMutationVariables:
    """Tests to verify DataConnect mutation variable requirements."""

    @pytest.mark.asyncio
    async def test_dataconnect_requires_all_declared_variables(self):
        """
        Regression test: DataConnect mutations require ALL declared variables
        to be present in the variables dict, even if they're optional (no !).

        Error: "$handbookVersionId is missing"
        Fix: Always include all variables, passing None for optional ones.
        """
        # This is a documentation test - the actual fix is in PlanService
        # The test above (test_create_plan_includes_all_optional_fields_as_none)
        # verifies the fix is in place.
        pass


class TestAdaptMilestones:
    """Tests for milestone adaptation logic."""

    @pytest.mark.asyncio
    async def test_adapt_milestones_calculates_cumulative_days(self):
        """Test that target_days is cumulative."""
        from services.plan_service import PlanService

        mock_db = MagicMock()
        service = PlanService(mock_db, "workspace-123")

        playbook_milestones = [
            {"title": "M1", "duration_days": 7, "owner_side": "us"},
            {"title": "M2", "duration_days": 14, "owner_side": "customer"},
            {"title": "M3", "duration_days": 10, "owner_side": "joint"},
        ]

        adapted = await service.adapt_milestones(
            playbook_milestones,
            deal_data={},
            gap_analysis={"timeline_feasible": True},
        )

        assert len(adapted) == 3
        assert adapted[0]["target_days"] == 7
        assert adapted[1]["target_days"] == 21  # 7 + 14
        assert adapted[2]["target_days"] == 31  # 7 + 14 + 10

    @pytest.mark.asyncio
    async def test_adapt_milestones_compresses_tight_timeline(self):
        """Test that tight timelines compress by 20%."""
        from services.plan_service import PlanService

        mock_db = MagicMock()
        service = PlanService(mock_db, "workspace-123")

        playbook_milestones = [
            {"title": "M1", "duration_days": 10, "owner_side": "us"},
        ]

        adapted = await service.adapt_milestones(
            playbook_milestones,
            deal_data={},
            gap_analysis={"timeline_feasible": False},  # Tight timeline
        )

        # 10 * 0.8 = 8 days
        assert adapted[0]["target_days"] == 8

    @pytest.mark.asyncio
    async def test_adapt_milestones_minimum_duration_is_3_days(self):
        """Test that compressed milestones have minimum 3 days."""
        from services.plan_service import PlanService

        mock_db = MagicMock()
        service = PlanService(mock_db, "workspace-123")

        playbook_milestones = [
            {"title": "M1", "duration_days": 3, "owner_side": "us"},
        ]

        adapted = await service.adapt_milestones(
            playbook_milestones,
            deal_data={},
            gap_analysis={"timeline_feasible": False},  # Tight timeline
        )

        # 3 * 0.8 = 2.4, but min is 3
        assert adapted[0]["target_days"] == 3
